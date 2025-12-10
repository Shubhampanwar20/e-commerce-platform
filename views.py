from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from .models import Product, Cart, CartItem, Order, UserInteraction, Category
from .recommendation_engine import RecommendationEngine
from .cart_utils import (
    get_cart_items, get_cart_total, add_to_session_cart,
    update_session_cart_item, remove_from_session_cart, clear_session_cart
)
from decimal import Decimal


def product_list(request):
    """Display all products with filtering options"""
    products = Product.objects.all()
    categories = Category.objects.all()
    
    # Filter by category
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        products = products.filter(name__icontains=search_query)
    
    context = {
        'products': products,
        'categories': categories,
        'selected_category': category_id,
        'search_query': search_query,
    }
    return render(request, 'store/product_list.html', context)


def product_detail(request, product_id):
    """Display product details and track view interaction"""
    product = get_object_or_404(Product, id=product_id)
    
    # Track view interaction if user is logged in
    if request.user.is_authenticated:
        UserInteraction.objects.get_or_create(
            user=request.user,
            product=product,
            interaction_type='view',
            defaults={'rating': None}
        )
    
    # Get recommendations (only for authenticated users)
    recommendations = []
    if request.user.is_authenticated:
        engine = RecommendationEngine()
        recommendations = engine.get_recommendations(request.user, num_recommendations=4)
    
    context = {
        'product': product,
        'recommendations': recommendations,
    }
    return render(request, 'store/product_detail.html', context)


def cart_view(request):
    """Display user's cart (works for both authenticated and anonymous users)"""
    cart_items, is_session, cart_obj = get_cart_items(request)
    total = get_cart_total(request)
    
    context = {
        'cart_items': cart_items,
        'total': total,
        'is_session_cart': is_session,
    }
    return render(request, 'store/cart.html', context)


@require_http_methods(["POST"])
def add_to_cart(request, product_id):
    """Add product to cart (works for both authenticated and anonymous users)"""
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity < 1:
        messages.error(request, 'Quantity must be at least 1')
        return redirect('product_detail', product_id=product_id)
    
    if quantity > product.stock:
        messages.error(request, f'Only {product.stock} items available in stock')
        return redirect('product_detail', product_id=product_id)
    
    if request.user.is_authenticated:
        # Authenticated user: use database cart
        cart, created = Cart.objects.get_or_create(user=request.user, is_active=True)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )
        
        if not created:
            cart_item.quantity += quantity
            if cart_item.quantity > product.stock:
                cart_item.quantity = product.stock
            cart_item.save()
        
        # Track interaction
        UserInteraction.objects.get_or_create(
            user=request.user,
            product=product,
            interaction_type='add_to_cart',
            defaults={'rating': None}
        )
    else:
        # Anonymous user: use session-based cart
        add_to_session_cart(request, product_id, quantity)
    
    messages.success(request, f'{product.name} added to cart')
    return redirect('cart')


@require_http_methods(["POST"])
def update_cart_item(request, product_id):
    """Update quantity of a cart item (works for both authenticated and anonymous users)"""
    quantity = int(request.POST.get('quantity', 1))
    product = get_object_or_404(Product, id=product_id)
    
    if request.user.is_authenticated:
        cart = get_object_or_404(Cart, user=request.user, is_active=True)
        cart_item = CartItem.objects.filter(cart=cart, product=product).first()
        
        if cart_item:
            if quantity < 1:
                cart_item.delete()
                messages.success(request, 'Item removed from cart')
            elif quantity > product.stock:
                messages.error(request, f'Only {product.stock} items available')
            else:
                cart_item.quantity = quantity
                cart_item.save()
                messages.success(request, 'Cart updated')
    else:
        # Session-based cart
        if quantity < 1:
            remove_from_session_cart(request, product_id)
            messages.success(request, 'Item removed from cart')
        elif quantity > product.stock:
            messages.error(request, f'Only {product.stock} items available')
        else:
            update_session_cart_item(request, product_id, quantity)
            messages.success(request, 'Cart updated')
    
    return redirect('cart')


@require_http_methods(["POST"])
def remove_from_cart(request, product_id):
    """Remove item from cart (works for both authenticated and anonymous users)"""
    product = get_object_or_404(Product, id=product_id)
    
    if request.user.is_authenticated:
        cart = get_object_or_404(Cart, user=request.user, is_active=True)
        cart_item = CartItem.objects.filter(cart=cart, product=product).first()
        if cart_item:
            cart_item.delete()
    else:
        remove_from_session_cart(request, product_id)
    
    messages.success(request, 'Item removed from cart')
    return redirect('cart')


def checkout(request):
    """Display checkout page (works for both authenticated and anonymous users)"""
    cart_items, is_session, _ = get_cart_items(request)
    
    if not cart_items:
        messages.warning(request, 'Your cart is empty')
        return redirect('cart')
    
    total = get_cart_total(request)
    
    context = {
        'cart_items': cart_items,
        'total': total,
        'is_session_cart': is_session,
        'is_authenticated': request.user.is_authenticated,
    }
    return render(request, 'store/checkout.html', context)


@transaction.atomic
def process_order(request):
    """Process the order (works for both authenticated and anonymous users)"""
    cart_items, is_session, _ = get_cart_items(request)
    
    if not cart_items:
        messages.warning(request, 'Your cart is empty')
        return redirect('cart')
    
    # Validate stock
    for item in cart_items:
        product = item['product'] if is_session else item.product
        quantity = item['quantity'] if is_session else item.quantity
        
        if quantity > product.stock:
            messages.error(request, f'Insufficient stock for {product.name}')
            return redirect('cart')
    
    # Get customer and shipping information
    if request.user.is_authenticated:
        customer_name = request.user.get_full_name() or request.user.username
        customer_email = request.user.email or request.POST.get('customer_email', '').strip()
        customer_phone = request.POST.get('phone', '')
        
        # Ensure email is provided for authenticated users too
        if not customer_email:
            customer_email = request.POST.get('customer_email', '').strip()
            if not customer_email:
                messages.error(request, 'Please provide your email address')
                return redirect('checkout')
    else:
        customer_name = request.POST.get('customer_name', '').strip()
        customer_email = request.POST.get('customer_email', '').strip()
        customer_phone = request.POST.get('customer_phone', '').strip()
        
        if not customer_name or not customer_email:
            messages.error(request, 'Please provide your name and email')
            return redirect('checkout')
        
        # Validate email format
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            validate_email(customer_email)
        except ValidationError:
            messages.error(request, 'Please provide a valid email address')
            return redirect('checkout')
    
    shipping_address = request.POST.get('shipping_address', '').strip()
    if not shipping_address:
        messages.error(request, 'Please provide a shipping address')
        return redirect('checkout')
    
    total = get_cart_total(request)
    
    # Create cart in database if it doesn't exist (for anonymous users)
    if is_session:
        # Create a temporary cart for the order
        cart = Cart.objects.create(user=None, is_active=False)
        for item in cart_items:
            CartItem.objects.create(
                cart=cart,
                product=item['product'],
                quantity=item['quantity']
            )
    else:
        cart = Cart.objects.get(user=request.user, is_active=True)
        cart.is_active = False
        cart.save()
    
    # Create order
    order = Order.objects.create(
        user=request.user if request.user.is_authenticated else None,
        cart=cart,
        customer_name=customer_name,
        customer_email=customer_email,
        customer_phone=customer_phone,
        total_amount=total,
        shipping_address=shipping_address,
        status='pending'
    )
    
    # Update stock and track purchases
    for item in cart_items:
        product = item['product'] if is_session else item.product
        quantity = item['quantity'] if is_session else item.quantity
        
        product.stock -= quantity
        product.save()
        
        # Track purchase interaction (only for authenticated users)
        if request.user.is_authenticated:
            UserInteraction.objects.get_or_create(
                user=request.user,
                product=product,
                interaction_type='purchase',
                defaults={'rating': None}
            )
    
    # Clear session cart if it was a guest checkout
    if is_session:
        clear_session_cart(request)
    
    messages.success(request, f'Order #{order.id} placed successfully!')
    return redirect('order_detail', order_id=order.id)


def order_detail(request, order_id):
    """Display order details"""
    order = get_object_or_404(Order, id=order_id)
    
    # Check if user has permission to view this order
    if request.user.is_authenticated:
        if order.user and order.user != request.user:
            messages.error(request, 'You do not have permission to view this order')
            return redirect('product_list')
    else:
        # For guest orders, we could use email verification or order number
        # For simplicity, we'll allow viewing by order ID
        pass
    
    # Get cart items
    if order.cart:
        cart_items = order.cart.items.all()
    else:
        cart_items = []
    
    context = {
        'order': order,
        'cart_items': cart_items,
    }
    return render(request, 'store/order_detail.html', context)


@login_required
def recommendations(request):
    """Display personalized product recommendations"""
    engine = RecommendationEngine()
    recommendations = engine.get_recommendations(request.user, num_recommendations=12)
    
    context = {
        'recommendations': recommendations,
    }
    return render(request, 'store/recommendations.html', context)


@login_required
@require_http_methods(["POST"])
def track_interaction(request, product_id):
    """Track user interactions (like/dislike) - requires login"""
    product = get_object_or_404(Product, id=product_id)
    interaction_type = request.POST.get('interaction_type')
    rating = request.POST.get('rating')
    
    if interaction_type not in ['like', 'dislike']:
        return JsonResponse({'error': 'Invalid interaction type'}, status=400)
    
    rating_float = None
    if rating:
        try:
            rating_float = float(rating)
            if rating_float < 0 or rating_float > 5:
                rating_float = None
        except ValueError:
            rating_float = None
    
    interaction, created = UserInteraction.objects.get_or_create(
        user=request.user,
        product=product,
        interaction_type=interaction_type,
        defaults={'rating': rating_float}
    )
    
    if not created and rating_float is not None:
        interaction.rating = rating_float
        interaction.save()
    
    return JsonResponse({
        'success': True,
        'message': f'Interaction recorded: {interaction_type}'
    })
