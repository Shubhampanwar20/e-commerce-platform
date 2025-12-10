from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Attributes for recommendation system
    brand = models.CharField(max_length=100, blank=True)
    rating = models.FloatField(default=0.0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")

    def __str__(self):
        return self.name


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='carts')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        if self.user:
            return f"Cart for {self.user.username}"
        else:
            return f"Guest Cart #{self.id}"

    @property
    def total(self):
        total_sum = sum(item.subtotal for item in self.items.all())
        return Decimal(str(total_sum)) if total_sum else Decimal('0.00')


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders')
    cart = models.OneToOneField(Cart, on_delete=models.SET_NULL, null=True, blank=True, related_name='order')
    # Guest checkout information
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    shipping_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        if self.user:
            return f"Order #{self.id} - {self.user.username}"
        else:
            return f"Order #{self.id} - {self.customer_name} (Guest)"


class UserInteraction(models.Model):
    INTERACTION_TYPES = [
        ('view', 'View'),
        ('like', 'Like'),
        ('dislike', 'Dislike'),
        ('add_to_cart', 'Add to Cart'),
        ('purchase', 'Purchase'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='interactions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='interactions')
    interaction_type = models.CharField(max_length=20, choices=INTERACTION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    rating = models.FloatField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(5)])

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', 'interaction_type']),
            models.Index(fields=['product', 'interaction_type']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.interaction_type} - {self.product.name}"
