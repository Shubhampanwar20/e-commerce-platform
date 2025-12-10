"""
Utility functions for cart management (supports both authenticated and anonymous users)
"""
from .models import Cart, CartItem, Product
from django.contrib.auth.models import AnonymousUser


def get_or_create_cart(request):
    """
    Get or create a cart for the current user (authenticated or anonymous)
    Uses session for anonymous users and database for authenticated users
    """
    if request.user.is_authenticated:
        # Authenticated user: use database cart
        cart, created = Cart.objects.get_or_create(user=request.user, is_active=True)
        return cart, False
    else:
        # Anonymous user: use session-based cart
        session_cart = request.session.get('cart', {})
        return session_cart, True


def get_cart_items(request):
    """
    Get cart items for the current user
    Returns tuple: (cart_items_list, is_session_cart, cart_obj_or_session_dict)
    """
    if request.user.is_authenticated:
        cart, _ = Cart.objects.get_or_create(user=request.user, is_active=True)
        cart_items = list(cart.items.select_related('product').all())
        return cart_items, False, cart
    else:
        # Session-based cart
        session_cart = request.session.get('cart', {})
        cart_items = []
        for product_id, quantity in session_cart.items():
            try:
                product = Product.objects.get(id=int(product_id))
                # Calculate subtotal directly
                subtotal = product.price * quantity
                # Create a simple object to represent cart item
                cart_items.append({
                    'product': product,
                    'quantity': quantity,
                    'product_id': product.id,
                    'subtotal': subtotal,
                })
            except Product.DoesNotExist:
                # Product was deleted, remove from cart
                if product_id in session_cart:
                    del session_cart[product_id]
                    request.session['cart'] = session_cart
                    request.session.modified = True
        
        return cart_items, True, session_cart


def get_cart_total(request):
    """
    Calculate total for the current cart
    """
    cart_items, is_session, _ = get_cart_items(request)
    if is_session:
        total = sum(item['subtotal'] for item in cart_items)
    else:
        total = sum(item.subtotal for item in cart_items)
    return total


def add_to_session_cart(request, product_id, quantity):
    """
    Add product to session-based cart
    """
    if 'cart' not in request.session:
        request.session['cart'] = {}
    
    cart = request.session['cart']
    product_id_str = str(product_id)
    
    if product_id_str in cart:
        cart[product_id_str] += quantity
    else:
        cart[product_id_str] = quantity
    
    request.session['cart'] = cart
    request.session.modified = True


def update_session_cart_item(request, product_id, quantity):
    """
    Update quantity in session-based cart
    """
    if 'cart' not in request.session:
        return False
    
    cart = request.session['cart']
    product_id_str = str(product_id)
    
    if product_id_str in cart:
        if quantity <= 0:
            del cart[product_id_str]
        else:
            cart[product_id_str] = quantity
        request.session['cart'] = cart
        request.session.modified = True
        return True
    return False


def remove_from_session_cart(request, product_id):
    """
    Remove product from session-based cart
    """
    if 'cart' not in request.session:
        return False
    
    cart = request.session['cart']
    product_id_str = str(product_id)
    
    if product_id_str in cart:
        del cart[product_id_str]
        request.session['cart'] = cart
        request.session.modified = True
        return True
    return False


def clear_session_cart(request):
    """
    Clear session-based cart
    """
    if 'cart' in request.session:
        del request.session['cart']
        request.session.modified = True

