from django.contrib import admin
from .models import Category, Product, Cart, CartItem, Order, UserInteraction


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'description']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock', 'rating', 'brand']
    list_filter = ['category', 'brand', 'rating']
    search_fields = ['name', 'description', 'brand']
    ordering = ['-created_at']


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['user__username']
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ['cart', 'product', 'quantity', 'subtotal']
    list_filter = ['cart__is_active']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'status', 'total_amount', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'id']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(UserInteraction)
class UserInteractionAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'interaction_type', 'rating', 'timestamp']
    list_filter = ['interaction_type', 'timestamp']
    search_fields = ['user__username', 'product__name']
    ordering = ['-timestamp']
