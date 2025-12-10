"""
Product Recommendation Engine using Collaborative Filtering and Content-Based Filtering
"""
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler
from django.contrib.auth.models import User
from django.db import models
from .models import Product, UserInteraction
from typing import List, Dict, Tuple
import math


class RecommendationEngine:
    """
    Main recommendation engine that combines multiple strategies
    """
    
    def __init__(self):
        self.scaler = StandardScaler()
        self.product_features_cache = {}
        self.user_product_matrix_cache = None
        
    def get_recommendations(self, user: User, num_recommendations: int = 10) -> List[Product]:
        """
        Get product recommendations for a user using hybrid approach
        """
        # Get user interactions
        user_interactions = UserInteraction.objects.filter(user=user)
        
        if not user_interactions.exists():
            # Cold start: return popular products
            return self._get_popular_products(num_recommendations)
        
        # Hybrid approach: combine collaborative and content-based
        collaborative_scores = self._collaborative_filtering(user, num_recommendations * 2)
        content_scores = self._content_based_filtering(user, num_recommendations * 2)
        
        # Combine scores (weighted average)
        combined_scores = self._combine_scores(collaborative_scores, content_scores, 0.6, 0.4)
        
        # Filter out products user has already interacted with
        viewed_products = set(user_interactions.values_list('product_id', flat=True))
        
        # Sort by score and return top recommendations
        recommendations = sorted(combined_scores.items(), key=lambda x: x[1], reverse=True)
        recommended_product_ids = [
            pid for pid, score in recommendations 
            if pid not in viewed_products
        ][:num_recommendations]
        
        return Product.objects.filter(id__in=recommended_product_ids)
    
    def _get_popular_products(self, num: int) -> List[Product]:
        """Return popular products based on interactions"""
        popular_products = Product.objects.annotate(
            view_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='view')),
            like_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='like')),
            purchase_count=models.Count('interactions', filter=models.Q(interactions__interaction_type='purchase'))
        ).annotate(
            popularity_score=(
                models.F('view_count') * 1 + 
                models.F('like_count') * 3 + 
                models.F('purchase_count') * 5
            )
        ).order_by('-popularity_score', '-rating')[:num]
        
        return list(popular_products)
    
    def _collaborative_filtering(self, user: User, num_candidates: int) -> Dict[int, float]:
        """
        Collaborative filtering: find users with similar preferences
        """
        try:
            from .cython_recommendations import compute_user_similarity_matrix
        except ImportError:
            # Fallback to pure Python if Cython module not available
            return self._collaborative_filtering_python(user, num_candidates)
        
        # Get all user interactions
        all_interactions = UserInteraction.objects.select_related('user', 'product').all()
        
        if not all_interactions.exists():
            return {}
        
        # Build user-product interaction matrix
        users = User.objects.all()
        products = Product.objects.all()
        
        user_map = {u.id: idx for idx, u in enumerate(users)}
        product_map = {p.id: idx for idx, p in enumerate(products)}
        
        # Create interaction matrix (dense for Cython)
        num_users = len(users)
        num_products = len(products)
        
        if num_users == 0 or num_products == 0:
            return {}
        
        # Build interaction scores
        interaction_matrix = np.zeros((num_users, num_products))
        
        for interaction in all_interactions:
            user_idx = user_map.get(interaction.user_id)
            product_idx = product_map.get(interaction.product_id)
            
            if user_idx is not None and product_idx is not None:
                # Weight different interaction types
                weights = {
                    'view': 1.0,
                    'like': 3.0,
                    'dislike': -2.0,
                    'add_to_cart': 4.0,
                    'purchase': 5.0,
                }
                score = weights.get(interaction.interaction_type, 1.0)
                if interaction.rating:
                    score *= (1 + interaction.rating / 5.0)
                interaction_matrix[user_idx, product_idx] = score
        
        # Use Cython-optimized similarity computation
        if user.id in user_map:
            user_idx = user_map[user.id]
            user_vector = interaction_matrix[user_idx]
            
            # Compute similarities using Cython
            similarities = compute_user_similarity_matrix(
                interaction_matrix.astype(np.float64),
                user_vector.astype(np.float64)
            )
            
            # Get similar users (excluding self)
            similar_users = []
            for other_user_id, other_idx in user_map.items():
                if other_user_id != user.id and similarities[other_idx] > 0:
                    similar_users.append((other_user_id, similarities[other_idx]))
            
            similar_users.sort(key=lambda x: x[1], reverse=True)
            
            # Recommend products liked by similar users
            scores = {}
            for similar_user_id, similarity in similar_users[:10]:  # Top 10 similar users
                similar_user_idx = user_map[similar_user_id]
                similar_user_vector = interaction_matrix[similar_user_idx]
                
                # Weight products by similarity
                for product_id, product_idx in product_map.items():
                    if user_vector[product_idx] == 0 and similar_user_vector[product_idx] > 0:
                        if product_id not in scores:
                            scores[product_id] = 0
                        scores[product_id] += similarity * similar_user_vector[product_idx]
            
            return scores
        
        return {}
    
    def _content_based_filtering(self, user: User, num_candidates: int) -> Dict[int, float]:
        """
        Content-based filtering: recommend similar products to what user likes
        """
        try:
            from .cython_recommendations import compute_product_similarity
        except ImportError:
            # Fallback to pure Python if Cython module not available
            return self._content_based_filtering_python(user, num_candidates)
        
        # Get user's liked/purchased products
        user_liked = UserInteraction.objects.filter(
            user=user,
            interaction_type__in=['like', 'purchase', 'add_to_cart']
        ).values_list('product_id', flat=True)
        
        if not user_liked:
            return {}
        
        # Get product features
        liked_products = Product.objects.filter(id__in=user_liked)
        all_products = Product.objects.all()
        
        if not liked_products.exists() or not all_products.exists():
            return {}
        
        # Build feature vectors for products
        product_features = {}
        for product in all_products:
            features = self._get_product_features(product)
            product_features[product.id] = features
        
        # Compute similarities using Cython
        liked_feature_vectors = np.array([
            product_features[pid] for pid in user_liked
        ]).astype(np.float64)
        
        scores = {}
        for product in all_products:
            if product.id not in user_liked:
                product_vector = np.array([product_features[product.id]]).astype(np.float64)
                similarity = compute_product_similarity(liked_feature_vectors, product_vector)
                scores[product.id] = float(np.max(similarity))  # Max similarity across all liked products
        
        return scores
    
    def _get_product_features(self, product: Product) -> List[float]:
        """
        Extract features from product for content-based filtering
        """
        if product.id in self.product_features_cache:
            return self.product_features_cache[product.id]
        
        # Feature vector: [price_normalized, rating, category_id, brand_hash, tag_count]
        features = []
        
        # Price (normalized to 0-1, assuming max price of 1000)
        max_price = 1000.0
        features.append(float(product.price) / max_price)
        
        # Rating (normalized to 0-1)
        features.append(product.rating / 5.0)
        
        # Category (one-hot encoded as numeric)
        category_val = hash(product.category.name if product.category else 'none') % 100 / 100.0
        features.append(category_val)
        
        # Brand (hashed)
        brand_val = hash(product.brand if product.brand else 'none') % 100 / 100.0
        features.append(brand_val)
        
        # Tag count (normalized)
        tag_count = len(product.tags.split(',')) if product.tags else 0
        features.append(min(tag_count / 10.0, 1.0))
        
        # Interaction stats
        from django.db.models import Count
        view_count = product.interactions.filter(interaction_type='view').count()
        like_count = product.interactions.filter(interaction_type='like').count()
        purchase_count = product.interactions.filter(interaction_type='purchase').count()
        
        features.append(min(view_count / 100.0, 1.0))
        features.append(min(like_count / 50.0, 1.0))
        features.append(min(purchase_count / 20.0, 1.0))
        
        self.product_features_cache[product.id] = features
        return features
    
    def _combine_scores(self, scores1: Dict[int, float], scores2: Dict[int, float], 
                       weight1: float, weight2: float) -> Dict[int, float]:
        """
        Combine two score dictionaries with weights
        """
        combined = {}
        all_products = set(scores1.keys()) | set(scores2.keys())
        
        # Normalize scores
        if scores1:
            max_score1 = max(scores1.values()) if scores1.values() else 1
            min_score1 = min(scores1.values()) if scores1.values() else 0
            range1 = max_score1 - min_score1 if max_score1 != min_score1 else 1
        else:
            range1 = 1
            min_score1 = 0
        
        if scores2:
            max_score2 = max(scores2.values()) if scores2.values() else 1
            min_score2 = min(scores2.values()) if scores2.values() else 0
            range2 = max_score2 - min_score2 if max_score2 != min_score2 else 1
        else:
            range2 = 1
            min_score2 = 0
        
        for product_id in all_products:
            score1 = ((scores1.get(product_id, 0) - min_score1) / range1) if range1 > 0 else 0
            score2 = ((scores2.get(product_id, 0) - min_score2) / range2) if range2 > 0 else 0
            combined[product_id] = weight1 * score1 + weight2 * score2
        
        return combined
    
    def _collaborative_filtering_python(self, user: User, num_candidates: int) -> Dict[int, float]:
        """Pure Python fallback for collaborative filtering"""
        # Simplified version for fallback
        user_interactions = UserInteraction.objects.filter(user=user)
        if not user_interactions.exists():
            return {}
        
        # Simple recommendation based on similar products
        scores = {}
        user_product_ids = set(user_interactions.values_list('product_id', flat=True))
        
        for interaction in user_interactions:
            # Find products with same category
            product = interaction.product
            similar_products = Product.objects.filter(
                category=product.category
            ).exclude(id__in=user_product_ids)
            
            for similar_product in similar_products:
                if similar_product.id not in scores:
                    scores[similar_product.id] = 0
                scores[similar_product.id] += 0.5
        
        return scores
    
    def _content_based_filtering_python(self, user: User, num_candidates: int) -> Dict[int, float]:
        """Pure Python fallback for content-based filtering"""
        user_liked = UserInteraction.objects.filter(
            user=user,
            interaction_type__in=['like', 'purchase', 'add_to_cart']
        ).values_list('product_id', flat=True)
        
        if not user_liked:
            return {}
        
        liked_products = list(Product.objects.filter(id__in=user_liked))
        all_products = Product.objects.exclude(id__in=user_liked)
        
        scores = {}
        for product in all_products:
            max_similarity = 0
            product_features = np.array(self._get_product_features(product))
            
            for liked_product in liked_products:
                liked_features = np.array(self._get_product_features(liked_product))
                similarity = cosine_similarity([product_features], [liked_features])[0][0]
                max_similarity = max(max_similarity, similarity)
            
            if max_similarity > 0:
                scores[product.id] = max_similarity
        
        return scores

