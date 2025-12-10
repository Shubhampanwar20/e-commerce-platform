"""
Context processors for store app
"""
from .models import Cart


def cart_context(request):
    """Add cart information to all templates"""
    context = {}
    if request.user.is_authenticated:
        try:
            cart = Cart.objects.get(user=request.user, is_active=True)
            context['cart_item_count'] = cart.items.count()
        except Cart.DoesNotExist:
            context['cart_item_count'] = 0
    else:
        # Count items in session cart
        session_cart = request.session.get('cart', {})
        context['cart_item_count'] = sum(1 for qty in session_cart.values() if qty > 0)
    return context

