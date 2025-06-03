# admin_panel/forms.py
from django import forms
from authentication.models import Product, Variant, ProductImage,Offer,Category, Product
from django.forms import inlineformset_factory
from django.utils import timezone
from django.core.exceptions import ValidationError


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'category', 'brand']


class VariantForm(forms.ModelForm):
    class Meta:
        model = Variant
        fields = ['ram', 'storage', 'color','price', 'stock']

    def clean_price(self):
        price = self.cleaned_data.get("price")
        if price is None or price <= 0:
            raise forms.ValidationError("Price must be greater than zero.")
        return price

    def clean_quantity(self):
        quantity = self.cleaned_data.get("quantity")
        if quantity is None or quantity < 0:
            raise forms.ValidationError("Quantity cannot be negative.")
        return quantity

VariantImageFormSet = inlineformset_factory(
    Variant,  # Parent model
    ProductImage,  # Child model
    fields=['image'],
    extra=6,  # Allow up to 6 images per variant
    min_num=3,  # Require at least 3 images
    max_num=6,  # Limit to 6 images
    validate_min=True,
    validate_max=True,
    can_delete=True
)

class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            'name', 'scope', 'category', 'product', 
            'offer_type', 'discount', 'start_date', 
            'end_date', 'status'
        ]
        widgets = {
            'start_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_date': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter only active and non-deleted categories
        self.fields['category'].queryset = Category.objects.filter(status=True, is_deleted=False)
        # Filter only active and non-deleted products
        self.fields['product'].queryset = Product.objects.filter(status=True, is_deleted=False)

    def clean(self):
        cleaned_data = super().clean()
        
        # Validate scope
        scope = cleaned_data.get('scope')
        category = cleaned_data.get('category')
        product = cleaned_data.get('product')
        
        if scope == 'CATEGORY':
            if not category:
                raise ValidationError("Category is required for category offer")
            # Ensure product is None for CATEGORY scope
            cleaned_data['product'] = None
        
        elif scope == 'PRODUCT':
            if not product:
                raise ValidationError("Product is required for product offer")
            # Ensure category is None for PRODUCT scope
            cleaned_data['category'] = None
        
        # Validate dates
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        
        if start_date and end_date:
            if start_date >= end_date:
                raise ValidationError("End date must be after start date")
            
            if start_date < timezone.now():
                raise ValidationError("Start date cannot be in the past")
        
        # Validate discount
        offer_type = cleaned_data.get('offer_type')
        discount = cleaned_data.get('discount')
        
        if offer_type == 'PERCENTAGE' and discount > 100:
            raise ValidationError("Percentage discount cannot exceed 100%")
        
        return cleaned_data