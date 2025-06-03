import sys
from io import BytesIO
from django.db.models import Sum, F
from PIL import Image as PILImage
from django.utils import timezone
from django.db import models
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import transaction
from decimal import Decimal
from django.core.validators import MinValueValidator, MaxValueValidator



# Custom User Manager
class CustomUserManager(BaseUserManager):
    def create_user(self, email, username,phone=None, password=None, **extra_fields):
        if not email:
            raise ValueError("Email field is required")
        if not username:
            raise ValueError("Username field is required")
        # if not phone:
        #     raise ValueError("Phone field is required")

        email = self.normalize_email(email)
        #extra_fields.setdefault('profile_image', 'default.jpg')
        user = self.model(email=email, username=username,  phone=phone,**extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, phone=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        return self.create_user(email, username, phone, password, **extra_fields)

# Custom User Model
class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=100, unique=True)
    profile_image = models.ImageField(upload_to='profile_images/',default='profile_images/default.jpg',blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)  
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email

class Category(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)  # True for active, False for inactive
    is_deleted = models.BooleanField(default=False)  # For soft delete
    created_at = models.DateTimeField(auto_now_add=True)  # Automatically set when created, for sorting by latest

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['-created_at']
    
class Brand(models.Model):
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)  # True = Active, False = Inactive
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    def __str__(self):
        return self.name
    
class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    status = models.BooleanField(default=True)
    stock = models.IntegerField(default=0)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE,null=True)
    is_deleted = models.BooleanField(default=False)  # For soft delete
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_blocked = models.BooleanField(default=False)
    def __str__(self):
        return self.name
    
    def delete(self, *args, **kwargs):
        self.is_deleted = True
        self.status = False
        self.save()

    def get_display_price(self):
        variant = self.variants.first()
        return variant.price if variant else Decimal('0.00')

    def save(self, *args, **kwargs):
        # Remove stock reference since it's no longer a field
        # If you need to log something, adjust accordingly
        print(f"Save called for Product: {self.name}")
        super().save(*args, **kwargs)

    class Meta:
        ordering = ['-created_at']
    
    @property
    def first_variant(self):
        return self.variants.first()
    
class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    ram = models.IntegerField()  # Changed to IntegerField to match HTML number input
    storage = models.IntegerField()  # Changed to IntegerField
    color = models.CharField(max_length=50,default='Unknown')
    price = models.DecimalField(max_digits=10, decimal_places=2,default=0.00)  # Added from HTML
    stock = models.PositiveIntegerField(default=0)  # Added from HTML
    


    def __str__(self):
        return f"{self.product.name} - {self.ram}GB/{self.storage}GB/{self.color}"
    
class ProductImage(models.Model):
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='product_images/')

    def save(self, *args, **kwargs):
        # Only process if it's a new instance and the image is a fresh upload
        if self.pk is None and self.image and not hasattr(self.image, 'path'):
            try:
                img = PILImage.open(self.image)  # Process fresh upload
                if img.mode in ('RGBA', 'LA'):
                    img = img.convert('RGB')
                width, height = img.size
                min_dimension = min(width, height)
                left = (width - min_dimension) // 2
                top = (height - min_dimension) // 2
                right = (width + min_dimension) // 2
                bottom = (height + min_dimension) // 2
                img = img.crop((left, top, right, bottom))
                img = img.resize((300, 300), PILImage.LANCZOS)
                output = BytesIO()
                img.save(output, format='JPEG', quality=85)
                output.seek(0)
                variant_id = self.variant.id if self.variant else 'new'
                name = f"cropped-{variant_id}-{int(timezone.now().timestamp())}.jpg"
                self.image = InMemoryUploadedFile(
                    output, 'ImageField', name,
                    'image/jpeg', sys.getsizeof(output), None
                )
            except Exception as e:
                raise ValueError(f"Image processing failed: {str(e)}")
        super().save(*args, **kwargs)
        print(f"Saved image path: {self.image.path}, URL: {self.image.url}")

    def __str__(self):
        return f"Image for {self.variant}"

class Address(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="addresses")
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    landmark = models.CharField(max_length=255, blank=True, null=True)
    district = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=10)
    phone = models.CharField(max_length=15)
    alternative_phone = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.city}, {self.state}"

    class Meta:
        ordering = ['-created_at']

class Cart(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="cart_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE)  # No null=True, blank=True
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.variant.product.name} ({self.quantity})"

    def save(self, *args, **kwargs):
        if self.quantity > self.variant.stock:
            self.quantity = self.variant.stock
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'variant']),
        ]


class Wishlist(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="wishlist_items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, null=True, blank=True, related_name="wishlist_items")
    added_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        variant_info = f" (Variant: {self.variant})" if self.variant else ""
        return f"{self.user.username} - {self.product.name}{variant_info}"

    class Meta:
        unique_together = ('user', 'product', 'variant')  # Updated to include variant
        ordering = ['-added_at']

class Order(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Confirmed', 'Confirmed'),
        ('Shipped', 'Shipped'),
        ('Delivered', 'Delivered'),
        ('Canceled', 'Canceled'),
        ('Return Requested', 'Return Requested'),
        ('Returned', 'Returned'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('COD', 'Cash on Delivery'),
        ('Wallet', 'Wallet'),
        ('Razorpay', 'Razorpay'),
    ]

    PAYMENT_STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Success', 'Success'),
        ('Failed', 'Failed'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="orders")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    transaction_id = models.CharField(max_length=255, blank=True, null=True)  # Only for Razorpay
    shipping_address = models.ForeignKey(Address, on_delete=models.CASCADE) 
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # New field
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='Pending', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def update_total_price(self):
        """Update total_price based on non-returned OrderItems"""
        self.total_price = sum(
            item.get_total_price() if item.price is not None and not item.is_returned else 0
            for item in self.items.all()
        )
        self.save()

    def check_all_items_returned(self):
        """Check if all items in the order are returned and update status"""
        if self.items.exists() and all(item.is_returned for item in self.items.all()):
            self.status = 'Returned'
            self.process_return()
        self.save()

    def delete(self, *args, **kwargs):
        """Soft delete by setting is_deleted=True and updating status"""
        self.is_deleted = True
        self.status = 'Canceled'  # Optionally set status to Canceled
        self.save()

    def save(self, *args, **kwargs):
        if self.pk:
            old_order = Order.objects.get(pk=self.pk)
            print(f"[SAVE] Order #{self.pk}: {old_order.status} -> {self.status}")
            if old_order.status != 'Returned' and self.status == 'Returned':
                print(f"[SAVE] Order #{self.pk} marked for return processing")
                super().save(*args, **kwargs)
                self.process_return()
            else:
                print(f"[SAVE] Order #{self.pk}: No return needed")
                super().save(*args, **kwargs)
        else:
            print(f"[SAVE] Creating new order")
            super().save(*args, **kwargs)

    
    def process_return(self):
        print(f"[RETURN] Starting process_return for Order #{self.id}, Status: {self.status}, Payment: {self.payment_method}")
        if self.status != 'Returned':
            print(f"[RETURN] Order #{self.id} not in 'Returned' status, skipping")
            return
        
        try:
            with transaction.atomic():
                # Build product details for transaction description
                product_details = ""
                for item in self.items.filter(is_returned=True):
                    variant_info = f" ({item.variant.ram}/{item.variant.storage}/{item.variant.color})" if item.variant else ""
                    product_details += f"{item.product.name}{variant_info} × {item.quantity}, "
                    # Update stock for returned items
                    if item.variant:
                        item.variant.stock += item.quantity
                        item.variant.save()
                        print(f"[RETURN] Updated stock for variant {item.variant} to {item.variant.stock}")
                    else:
                        item.product.stock += item.quantity
                        item.product.save()
                        print(f"[RETURN] Updated stock for product {item.product} to {item.product.stock}")
                
                product_details = product_details.rstrip(", ") or "No items"
                print(f"[RETURN] Product details: {product_details}")
                
                # Update wallet for returned items
                total_returned_amount = sum(
                    item.get_total_price() for item in self.items.filter(is_returned=True)
                )
                if total_returned_amount > 0:
                    wallet, created = Wallet.objects.get_or_create(user=self.user)
                    print(f"[RETURN] Wallet before: {wallet.balance}, Total Returned Amount: {total_returned_amount}")
                    wallet.balance += Decimal(str(total_returned_amount))
                    wallet.save()
                    print(f"[RETURN] Wallet after: {wallet.balance}")
                    
                    # Create transaction record
                    import uuid
                    unique_ref = str(uuid.uuid4())
                    txn = Transaction.objects.create(
                        wallet=wallet,
                        amount=total_returned_amount,
                        transaction_type='CREDIT',
                        description=f"Refund for returned items in order #{self.id}: {product_details}",
                        order=self
                    )
                    print(f"[RETURN] Transaction created: ID {txn.id}")
        except Exception as e:
            print(f"[RETURN] Error in process_return for Order #{self.id}: {str(e)}")
            raise
   
    
    def calculate_total_price(self):
        return self.total_price + self.shipping_fee

    def __str__(self):
        return f"Order {self.id} - {self.user.email} - {self.status}"



class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(Variant, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    is_returned = models.BooleanField(default=False)  
    return_reason = models.TextField(blank=True, null=True)

    def get_total_price(self):
        """Calculate the total price for this item"""
        return self.quantity * self.price if self.price is not None else 0

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.order.update_total_price()
        self.order.check_all_items_returned()

    def __str__(self):
        return f"{self.product.name} - {self.quantity} pcs"

    class Meta:
        ordering = ['order']

class Wallet(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='wallet',
        primary_key=True
    )
    balance = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Current balance in the wallet"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Wallet - ₹{self.balance}"

    def add_funds(self, amount, description=None, order=None):
        """Add funds to the wallet and create a transaction."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        self.balance += Decimal(str(amount))
        self.save()
        
        # Use provided description or default
        if description is None:
            description = "Funds added to wallet"
        
        # Create transaction record
        transaction = Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='CREDIT',
            description=description,
            order=order
        )
        
        return transaction

    def deduct_funds(self, amount, order=None):
        """Deduct funds from the wallet and create a transaction."""
        if amount <= 0:
            raise ValueError("Amount must be positive")
        if self.balance < amount:
            raise ValueError("Insufficient wallet balance")
        self.balance -= Decimal(str(amount))
        self.save()
        Transaction.objects.create(
            wallet=self,
            amount=amount,
            transaction_type='DEBIT',
            description="Payment for order" if order else "Funds deducted",
            order=order
        )

    class Meta:
        ordering = ['-created_at']


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('CREDIT', 'Credit'),  # Funds added to wallet
        ('DEBIT', 'Debit'),    # Funds deducted from wallet
    ]

    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.CASCADE,
        related_name='transactions'
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount of the transaction"
    )
    transaction_type = models.CharField(
        max_length=6,
        choices=TRANSACTION_TYPES,
        help_text="Type of transaction: Credit or Debit"
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Description of the transaction"
    )
    order = models.ForeignKey(
        'Order',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
        help_text="Associated order, if applicable"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type} of ₹{self.amount} for {self.wallet.user.username} - {self.created_at}"

    class Meta:
        ordering = ['-created_at']

class Offer(models.Model):
    OFFER_TYPES = [
        ('PERCENTAGE', 'Percentage Discount'),
        ('FIXED', 'Fixed Amount Discount'),
    ]

    OFFER_SCOPES = [
        ('PRODUCT', 'Product Specific'),
        ('CATEGORY', 'Category Wide'),
    ]

    # Common fields for all offers
    name = models.CharField(max_length=255, help_text="Name of the offer")
    offer_type = models.CharField(
        max_length=20, 
        choices=OFFER_TYPES, 
        help_text="Type of discount (Percentage or Fixed)"
    )
    discount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        validators=[MinValueValidator(0)],
        help_text="Discount amount or percentage"
    )
    start_date = models.DateTimeField(help_text="Start date of the offer")
    end_date = models.DateTimeField(help_text="End date of the offer")
    status = models.BooleanField(default=True, help_text="Active or Inactive offer")

    # Scope-specific fields
    scope = models.CharField(
        max_length=20, 
        choices=OFFER_SCOPES, 
        help_text="Scope of the offer (Product or Category)"
    )
    
    # Optional foreign keys based on scope
    product = models.ForeignKey(
        'Product', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        help_text="Product for product-specific offer"
    )
    category = models.ForeignKey(
        'Category', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        help_text="Category for category-wide offer"
    )

    def clean(self):
        """
        Validate offer creation:
        - Ensure only one of product or category is set based on scope
        - Validate date range
        - Validate discount value
        """
        from django.core.exceptions import ValidationError
        
        # Validate scope-specific constraints
        if self.scope == 'PRODUCT' and not self.product:
            raise ValidationError("Product must be specified for product-specific offer")
        
        if self.scope == 'CATEGORY' and not self.category:
            raise ValidationError("Category must be specified for category-wide offer")
        
        # Ensure start date is before end date
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Start date must be before end date")
        
        # Validate percentage discount
        if self.offer_type == 'PERCENTAGE' and self.discount > 100:
            raise ValidationError("Percentage discount cannot exceed 100%")

    def is_currently_active(self):
        """
        Check if the offer is currently valid and active
        """
        now = timezone.now()
        return (
            self.status and 
            self.start_date <= now <= self.end_date
        )

    def __str__(self):
        scope_details = self.product.name if self.scope == 'PRODUCT' else self.category.name
        return f"{self.name} - {self.get_scope_display()}: {scope_details}"

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=(
                    (models.Q(scope='PRODUCT') & models.Q(product__isnull=False) & models.Q(category__isnull=True)) |
                    (models.Q(scope='CATEGORY') & models.Q(category__isnull=False) & models.Q(product__isnull=True))
                ),
                name='valid_offer_scope'
            )
        ]
        ordering = ['-start_date']  

    def get_total_offer(self, product):
        """
        Calculate the total offer for a given product by comparing product-specific FED
        and category-wide offers, returning the maximum discount if both exist, or the single
        available discount if only one applies.
        
        Args:
            product (Product): The product to check offers for.
        
        Returns:
            Decimal: The maximum applicable discount, or 0 if no offers apply.
        """
        from django.utils import timezone
        
        now = timezone.now()
        
        # Get product-specific offer
        product_offer = Offer.objects.filter(
            scope='PRODUCT',
            product=product,
            status=True,
            start_date__lte=now,
            end_date__gte=now
        ).first()
        
        # Get category-wide offer
        category_offer = Offer.objects.filter(
            scope='CATEGORY',
            category=product.category,
            status=True,
            start_date__lte=now,
            end_date__gte=now
        ).first()
        
        # Calculate discounts
        product_discount = Decimal('0.00')
        if product_offer:
            if product_offer.offer_type == 'PERCENTAGE':
                product_discount = (product_offer.discount / Decimal('100.0')) * product.variants.first().price
            else:  # FIXED
                product_discount = product_offer.discount
        
        category_discount = Decimal('0.00')
        if category_offer:
            if category_offer.offer_type == 'PERCENTAGE':
                category_discount = (category_offer.discount / Decimal('100.0')) * product.variants.first().price
            else:  # FIXED
                category_discount = category_offer.discount
        
        # Return the maximum discount, or 0 if no offers apply
        return max(product_discount, category_discount) if (product_offer or category_offer) else Decimal('0.00')
    
class Coupon(models.Model):
    DISCOUNT_TYPES = [
        ('PERCENTAGE', 'Percentage Discount'),
        ('FIXED', 'Fixed Amount Discount'),
    ]
    
    code = models.CharField(max_length=50, unique=True, help_text="Unique coupon code")
    description = models.TextField(blank=True, null=True, help_text="Description of the coupon")
    discount_type = models.CharField(
        max_length=20, 
        choices=DISCOUNT_TYPES, 
        default='PERCENTAGE',
        help_text="Type of discount (Percentage or Fixed amount)"
    )
    discount_value = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Value of the discount (percentage or fixed amount)"
    )
    min_purchase_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        validators=[MinValueValidator(0)],
        help_text="Minimum purchase amount required to use this coupon"
    )
    max_discount_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        null=True, 
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Maximum discount amount (for percentage discounts)"
    )
    valid_from = models.DateTimeField(help_text="Start date and time of coupon validity")
    valid_until = models.DateTimeField(help_text="End date and time of coupon validity")
    usage_limit = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Total number of times this coupon can be used (null for unlimited)"
    )
    usage_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this coupon has been used"
    )
    per_user_limit = models.PositiveIntegerField(
        default=1,
        help_text="Number of times a single user can use this coupon"
    )
    is_active = models.BooleanField(default=True, help_text="Whether this coupon is currently active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.code} - {self.get_discount_type_display()} ({self.discount_value})"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        from django.utils import timezone
        
        # Validate date range
        if self.valid_from and self.valid_until and self.valid_from >= self.valid_until:
            raise ValidationError("Start date must be before end date")
        
        # Validate percentage discount
        if self.discount_type == 'PERCENTAGE' and self.discount_value > 100:
            raise ValidationError("Percentage discount cannot exceed 100%")
            
        # Validate max_discount_amount for percentage discounts
        if self.discount_type == 'PERCENTAGE' and not self.max_discount_amount:
            raise ValidationError("Maximum discount amount is required for percentage discounts")
    
    def is_valid(self, user=None, cart_total=None):
        """
        Check if the coupon is currently valid and can be applied
        
        Args:
            user (CustomUser, optional): The user applying the coupon
            cart_total (Decimal, optional): The total cart amount
            
        Returns:
            tuple: (is_valid (bool), error_message (str or None))
        """
        now = timezone.now()
        
        # Check if coupon is active
        if not self.is_active:
            return False, "This coupon is inactive"
            
        # Check date validity
        if now < self.valid_from:
            return False, "This coupon is not yet valid"
            
        if now > self.valid_until:
            return False, "This coupon has expired"
            
        # Check usage limits
        if self.usage_limit is not None and self.usage_count >= self.usage_limit:
            return False, "This coupon has reached its usage limit"
            
        # Check user-specific validity if user is provided
        if user:
            # Check per-user limit
            user_usage_count = CouponUsage.objects.filter(
                coupon=self,
                user=user
            ).count()
            
            if user_usage_count >= self.per_user_limit:
                return False, "You have already used this coupon the maximum number of times"
        
        # Check minimum purchase amount if cart_total is provided
        if cart_total is not None and cart_total < self.min_purchase_amount:
            return False, f"Minimum purchase of ₹{self.min_purchase_amount} required to use this coupon"
            
        return True, None
    
    def calculate_discount(self, amount):
        """
        Calculate the discount amount for a given purchase amount
        
        Args:
            amount (Decimal): The amount to apply the discount to
            
        Returns:
            Decimal: The discount amount
        """
        if self.discount_type == 'PERCENTAGE':
            discount = (self.discount_value / 100) * amount
            # Apply max discount cap if set
            if self.max_discount_amount and discount > self.max_discount_amount:
                return self.max_discount_amount
            return discount
        else:  # FIXED
            return min(self.discount_value, amount)  # Don't exceed the cart total
            
    class Meta:
        ordering = ['-created_at']


class CouponUsage(models.Model):
    """Track individual usage of coupons by users"""
    coupon = models.ForeignKey(
        Coupon, 
        on_delete=models.CASCADE,
        related_name='usages'
    )
    user = models.ForeignKey(
        'CustomUser',
        on_delete=models.CASCADE,
        related_name='coupon_usages'
    )
    order = models.ForeignKey(
        'Order',
        on_delete=models.SET_NULL,
        null=True,
        related_name='coupon_usages'
    )
    used_at = models.DateTimeField(auto_now_add=True)
    discount_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount discounted by this coupon"
    )
    
    def __str__(self):
        return f"{self.coupon.code} used by {self.user.username} on {self.used_at}"
    
    class Meta:
        unique_together = ('coupon', 'order')
        ordering = ['-used_at']