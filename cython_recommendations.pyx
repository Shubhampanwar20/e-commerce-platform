"""
Cython-optimized recommendation algorithms for high-performance computations
"""
import numpy as np
cimport numpy as np
cimport cython
from libc.math cimport sqrt

# Define data types
DTYPE = np.float64
ctypedef np.float64_t DTYPE_t

@cython.boundscheck(False)
@cython.wraparound(False)
def compute_user_similarity_matrix(np.ndarray[DTYPE_t, ndim=2] user_product_matrix, 
                                    np.ndarray[DTYPE_t, ndim=1] user_vector):
    """
    Compute cosine similarity between a user vector and all users in the matrix.
    This is optimized with Cython for performance.
    
    Parameters:
    -----------
    user_product_matrix : 2D numpy array (num_users x num_products)
        Matrix containing user-product interactions
    user_vector : 1D numpy array (num_products)
        Vector representing a single user's interactions
    
    Returns:
    --------
    similarities : 1D numpy array (num_users)
        Cosine similarities between user_vector and each user in the matrix
    """
    cdef int num_users = user_product_matrix.shape[0]
    cdef int num_products = user_product_matrix.shape[1]
    cdef np.ndarray[DTYPE_t, ndim=1] similarities = np.zeros(num_users, dtype=DTYPE)
    
    cdef int i, j
    cdef DTYPE_t dot_product, norm_user, norm_other, similarity
    cdef DTYPE_t user_norm_sq = 0.0
    
    # Pre-compute user vector norm
    for j in range(num_products):
        user_norm_sq += user_vector[j] * user_vector[j]
    norm_user = sqrt(user_norm_sq)
    
    if norm_user == 0.0:
        return similarities
    
    # Compute similarities with all other users
    for i in range(num_users):
        dot_product = 0.0
        norm_other_sq = 0.0
        
        # Compute dot product and norm simultaneously
        for j in range(num_products):
            dot_product += user_vector[j] * user_product_matrix[i, j]
            norm_other_sq += user_product_matrix[i, j] * user_product_matrix[i, j]
        
        norm_other = sqrt(norm_other_sq)
        
        # Compute cosine similarity
        if norm_other > 0.0:
            similarity = dot_product / (norm_user * norm_other)
            similarities[i] = similarity
    
    return similarities


@cython.boundscheck(False)
@cython.wraparound(False)
def compute_product_similarity(np.ndarray[DTYPE_t, ndim=2] liked_features,
                                np.ndarray[DTYPE_t, ndim=2] product_features):
    """
    Compute cosine similarity between product features and liked product features.
    Optimized with Cython for performance.
    
    Parameters:
    -----------
    liked_features : 2D numpy array (num_liked_products x num_features)
        Feature vectors of products the user liked
    product_features : 2D numpy array (1 x num_features)
        Feature vector of the product to compare
    
    Returns:
    --------
    similarities : 1D numpy array (num_liked_products)
        Cosine similarities between product and each liked product
    """
    cdef int num_liked = liked_features.shape[0]
    cdef int num_features = liked_features.shape[1]
    cdef np.ndarray[DTYPE_t, ndim=1] similarities = np.zeros(num_liked, dtype=DTYPE)
    
    cdef int i, j
    cdef DTYPE_t dot_product, norm_product, norm_liked, similarity
    cdef DTYPE_t product_norm_sq = 0.0
    
    # Pre-compute product feature norm
    for j in range(num_features):
        product_norm_sq += product_features[0, j] * product_features[0, j]
    norm_product = sqrt(product_norm_sq)
    
    if norm_product == 0.0:
        return similarities
    
    # Compute similarities with all liked products
    for i in range(num_liked):
        dot_product = 0.0
        norm_liked_sq = 0.0
        
        # Compute dot product and norm simultaneously
        for j in range(num_features):
            dot_product += product_features[0, j] * liked_features[i, j]
            norm_liked_sq += liked_features[i, j] * liked_features[i, j]
        
        norm_liked = sqrt(norm_liked_sq)
        
        # Compute cosine similarity
        if norm_liked > 0.0:
            similarity = dot_product / (norm_product * norm_liked)
            similarities[i] = similarity
    
    return similarities


@cython.boundscheck(False)
@cython.wraparound(False)
def compute_dot_product_batch(np.ndarray[DTYPE_t, ndim=2] matrix_a,
                               np.ndarray[DTYPE_t, ndim=2] matrix_b):
    """
    Compute batch dot products between two matrices efficiently.
    Useful for computing multiple similarities at once.
    
    Parameters:
    -----------
    matrix_a : 2D numpy array (n x m)
    matrix_b : 2D numpy array (k x m)
    
    Returns:
    --------
    result : 2D numpy array (n x k)
        Dot products between each row of A and each row of B
    """
    cdef int n = matrix_a.shape[0]
    cdef int k = matrix_b.shape[0]
    cdef int m = matrix_a.shape[1]
    cdef np.ndarray[DTYPE_t, ndim=2] result = np.zeros((n, k), dtype=DTYPE)
    
    cdef int i, j, idx
    cdef DTYPE_t dot_product
    
    for i in range(n):
        for j in range(k):
            dot_product = 0.0
            for idx in range(m):
                dot_product += matrix_a[i, idx] * matrix_b[j, idx]
            result[i, j] = dot_product
    
    return result

