from django.shortcuts import render,get_object_or_404,redirect
from authentication.models import Product, Category, Brand,Address,Wishlist,Cart,Order,OrderItem,Wallet, Transaction,Variant,ProductImage,Offer,Coupon,CouponUsage
from django.contrib.auth.decorators import user_passes_test
from .decorators import active_user_required
from .forms import UserEditForm,AddressForm
from django.http import JsonResponse
from django.contrib import messages
from django.urls import reverse
import json
import logging
logger = logging.getLogger(__name__)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from django.db import transaction
from django.views.decorators.csrf import csrf_protect   
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image as ReportLabImage
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,Image
import os
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.views.decorators.cache import never_cache
from decimal import Decimal
from django.db.models import DecimalField
from django.db.models.functions import Cast
from django.db.models import Min
from django.db.models import Prefetch, Sum
from django.db import models
import razorpay
from django.conf import settings
from django.views.decorators.cache import cache_control
import hmac
import hashlib
razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

@cache_control(no_cache=True, must_revalidate=True, no_store=True)
@active_user_required
def home(request):
    try:
        # Fetch all active categories that are not deleted
        categories = Category.objects.filter(status=True, is_deleted=False).order_by('name')
        brands = Brand.objects.filter(status=True).order_by('name')

        # Dictionary to hold paginated products for each category
        category_products = {}

        for category in categories:
            # Fetch products for the current category with prefetch for performance
            products = Product.objects.filter(
                category=category, status=True, is_deleted=False
            ).prefetch_related('variants__images')

            # Only include category if it has products
            if products.exists():
                # Paginate products for this category (5 products per page)
                paginator = Paginator(products, 5)
                # Use a unique query parameter for each category's pagination
                page_number = request.GET.get(f'page_{category.id}')
                paginated_products = paginator.get_page(page_number)

                # Store in dictionary with category as key
                category_products[category] = paginated_products

    except Exception as e:
        print(f"Error fetching data: {e}")
        category_products = {}
        brands = Brand.objects.none()

    # Paginate brands
    paginator_brands = Paginator(brands, 6)
    page_number_brands = request.GET.get('page_brands')
    brands_paginated = paginator_brands.get_page(page_number_brands)

    context = {
        'category_products': category_products,
        'brands': brands_paginated,
        'is_authenticated': request.user.is_authenticated,
        'query': request.GET.get('query', '')  # Pass search query if needed
    }
    return render(request, 'home.html', context)

@active_user_required
def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, status=True, is_deleted=False)
    
    # Get product-specific and category-wide offers
    product_offer = Offer.objects.filter(
        scope='PRODUCT',
        product=product,
        status=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).first()

    category_offer = Offer.objects.filter(
        scope='CATEGORY',
        category=product.category,
        status=True,
        start_date__lte=timezone.now(),
        end_date__gte=timezone.now()
    ).first()

    # Get the first variant for price calculation
    first_variant = product.variants.first()
    original_price = first_variant.price if first_variant else Decimal('0.00')

    # Calculate discounts for both offers
    product_discount = Decimal('0.00')
    if product_offer:
        if product_offer.offer_type == 'PERCENTAGE':
            product_discount = (product_offer.discount / Decimal('100.0')) * original_price
        else:  # FIXED
            product_discount = product_offer.discount

    category_discount = Decimal('0.00')
    if category_offer:
        if category_offer.offer_type == 'PERCENTAGE':
            category_discount = (category_offer.discount / Decimal('100.0')) * original_price
        else:  # FIXED
            category_discount = category_offer.discount

    # Select the offer with the greatest discount
    if product_discount > category_discount:
        best_offer = product_offer
        total_offer = product_discount
    else:
        best_offer = category_offer
        total_offer = category_discount

    # Calculate discount percentage if there's a valid offer
    discount_percentage = 0
    if total_offer > 0 and original_price > 0:
        discount_percentage = int((total_offer / original_price) * 100)

    # Calculate discounted price
    discounted_price = original_price - total_offer if original_price > total_offer else original_price

    # Get related models (products from the same brand, excluding the current product)
    related_models = Product.objects.filter(
        category=product.category,
        brand=product.brand,
        status=True,
        is_deleted=False
    ).exclude(id=product_id)[:4]

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'quantity': first_variant.stock if first_variant else 0
        })

    context = {
        'product': product,
        'offers': [best_offer] if best_offer else [],  # Pass only the best offer (or empty list)
        'original_price': original_price,
        'discounted_price': discounted_price,
        'discount_percentage': discount_percentage,
        'related_models': related_models,
        'is_authenticated': request.user.is_authenticated
    }
    return render(request, 'product_detail.html', context)

@active_user_required
def shop_page(request):
    try:
        # Fetch all active categories that are not deleted
        categories = Category.objects.filter(status=True, is_deleted=False).order_by('name')
        unique_brands = Brand.objects.filter(status=True).values_list('name', flat=True).distinct()

        # Dictionary to hold paginated products for each category
        category_products = {}

        # Get filter and sort parameters
        category_filter = request.GET.get('category', None)
        brand_filter = request.GET.get('brand', None)
        sort = request.GET.get('sort', None)

        # Determine which categories to process
        if category_filter:
            # Only process the selected category
            categories = categories.filter(name=category_filter)
        # If no category filter, process all categories

        for category in categories:
            # Fetch products for the current category
            products = Product.objects.filter(
                category=category, status=True, is_deleted=False
            ).prefetch_related('variants__images')

            # Apply brand filter
            if brand_filter:
                products = products.filter(brand__name=brand_filter)

            # Only include category if it has products after filtering
            if products.exists():
                # Apply sorting
                if sort:
                    if sort == 'price_low':
                        products = products.annotate(min_price=Min('variants__price')).order_by('min_price')
                    elif sort == 'price_high':
                        products = products.annotate(min_price=Min('variants__price')).order_by('-min_price')
                    elif sort == 'a_z':
                        products = products.order_by('name')
                    elif sort == 'z_a':
                        products = products.order_by('-name')

                # Paginate products for this category (5 products per page)
                paginator = Paginator(products, 5)
                page_number = request.GET.get(f'page_{category.id}', 1)
                paginated_products = paginator.get_page(page_number)

                # Store in dictionary with category as key
                category_products[category] = paginated_products

    except Exception as e:
        print(f"Error fetching data: {e}")
        category_products = {}
        unique_brands = Brand.objects.none()

    context = {
        'category_products': category_products,
        'sort': sort,
        'category': category_filter,
        'brand': brand_filter,
        'unique_brands': unique_brands,
        'unique_categories': Category.objects.filter(status=True, is_deleted=False),  # All categories for filter dropdown
        'is_authenticated': request.user.is_authenticated
    }
    return render(request, 'shop.html', context)


@active_user_required
def search_products(request):
    query = request.GET.get('query', '')
    sort = request.GET.get('sort', '')
    category_filter = request.GET.get('category', '')
    brand_filter = request.GET.get('brand', '')
    is_admin = request.user.is_staff or request.user.is_superuser

    # Dictionary to hold paginated products for each category
    category_products = {}
    unique_brands = Product.objects.filter(is_deleted=False).values_list('brand__name', flat=True).distinct()

    if query:
        try:
            # Define product filter for non-admin users
            product_filter = {'is_deleted': False}
            if not is_admin:
                product_filter['is_blocked'] = False
                product_filter['status'] = True

            # Fetch all active categories
            categories = Category.objects.filter(status=True, is_deleted=False).order_by('name')

            # Apply category filter if provided
            if category_filter:
                categories = categories.filter(name=category_filter)

            for category in categories:
                # Fetch products for the current category matching the query
                products = Product.objects.filter(
                    name__icontains=query,
                    category=category,
                    **product_filter
                ).prefetch_related('variants__images')

                # Apply brand filter
                if brand_filter:
                    products = products.filter(brand__name=brand_filter)

                # Only include category if it has products
                if products.exists():
                    # Apply sorting
                    if sort:
                        if sort == 'price_low':
                            products = products.annotate(min_price=Min('variants__price')).order_by('min_price')
                        elif sort == 'price_high':
                            products = products.annotate(max_price=Max('variants__price')).order_by('-max_price')
                        elif sort == 'a_z':
                            products = products.order_by('name')
                        elif sort == 'z_a':
                            products = products.order_by('-name')

                    # Paginate products for this category (5 products per page)
                    paginator = Paginator(products, 5)
                    page_number = request.GET.get(f'page_{category.id}', 1)
                    paginated_products = paginator.get_page(page_number)

                    # Store in dictionary with category as key
                    category_products[category] = paginated_products

        except Exception as e:
            print(f"Error in search: {str(e)}")

    context = {
        'category_products': category_products,
        'query': query,
        'sort': sort,
        'category': category_filter,
        'brand': brand_filter,
        'unique_brands': unique_brands,
        'unique_categories': Category.objects.filter(status=True, is_deleted=False),
        'is_authenticated': request.user.is_authenticated,
    }
    return render(request, 'search_results.html', context)


def brand_products(request, brand_id):
    brand = get_object_or_404(Brand, id=brand_id)
    products = Product.objects.filter(brand=brand, status=True)
    return render(request, 'brand_products.html', {'brand': brand, 'products': products})


# @active_user_required
# def mobile_details(request, product_id):
#     product = get_object_or_404(Product, id=product_id, category__name='Mobile')  # Assuming 'Phones' is the category name for mobiles
    
#     # Get offers for this product
#     offers = Offer.objects.filter(
#         models.Q(product=product) | models.Q(category=product.category),
#         status=True,
#         start_date__lte=timezone.now(),
#         end_date__gte=timezone.now()
#     )
    
#     # Get the first variant to calculate the price
#     first_variant = product.variants.first()
#     original_price = first_variant.price if first_variant else Decimal('0.00')

#     # Calculate the total offer discount
#     total_offer = Decimal('0.00')
#     discount_percentage = 0
#     if offers.exists():
#         total_offer = Offer.get_total_offer(Offer, product)  # Assuming this method exists in your Offer model
#         if total_offer > 0 and original_price > 0:
#             discount_percentage = int((total_offer / original_price) * 100)

#     # Calculate the discounted price
#     discounted_price = original_price - total_offer if original_price > total_offer else original_price

#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         return JsonResponse({
#             'quantity': first_variant.stock if first_variant else 0  # Return stock from variant
#         })

#     return render(request, 'mobile product page.html', {
#         'product': product,
#         'offers': offers,
#         'original_price': original_price,
#         'discounted_price': discounted_price,
#         'discount_percentage': discount_percentage,
#         'is_authenticated': request.user.is_authenticated  
#     })


# @active_user_required
# def laptop_detail(request, laptop_id):
    
#     laptop = get_object_or_404(Product, id=laptop_id, category__name='Laptop')
    
#     # Get offers for this laptop
#     offers = Offer.objects.filter(
#         models.Q(product=laptop) | models.Q(category=laptop.category),
#         status=True,
#         start_date__lte=timezone.now(),
#         end_date__gte=timezone.now()
#     )
    
#     # Get the first variant to calculate the price
#     first_variant = laptop.variants.first()
#     original_price = first_variant.price if first_variant else Decimal('0.00')

#     # Calculate the total offer discount
#     total_offer = Decimal('0.00')
#     discount_percentage = 0
#     if offers.exists():
#         total_offer = Offer.get_total_offer(Offer, laptop)  # Corrected call
#         if total_offer > 0 and original_price > 0:
#             discount_percentage = int((total_offer / original_price) * 100)

#     # Calculate the discounted price
#     discounted_price = original_price - total_offer if original_price > total_offer else original_price

#     # Get related models - laptops from the same brand
#     related_models = Product.objects.filter(
#         category__name='Laptop',
#         brand=laptop.brand
#     ).exclude(id=laptop.id)[:4]

#     return render(request, 'laptop_detail page.html', {
#         'laptop': laptop,
#         'offers': offers,
#         'related_models': related_models,
#         'original_price': original_price,
#         'discounted_price': discounted_price,
#         'discount_percentage': discount_percentage
#     })
    
def account_profile(request):
    return render(request, 'account_details.html', {'user': request.user})

@login_required
def update_account_profile(request):
    logger.info(f"Request received: {request.method}, Headers: {dict(request.headers)}")
    
    if not request.user.is_authenticated:
        logger.warning("User not authenticated")
        return JsonResponse({"success": False, "errors": {"auth": ["User not authenticated"]}}, status=401)

    if request.method == "POST":
        logger.debug(f"POST data: {request.POST}, FILES: {request.FILES}")
        form = UserEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            logger.info(f"Profile updated for user: {user.username}, Profile Image: {user.profile_image}")
            
            # Temporarily force JSON response for POST requests
            return JsonResponse({
                "success": True,
                "username": user.username,
                "email": user.email,
                "profile_image": user.profile_image.url if user.profile_image else None
            })
        else:
            logger.error(f"Form validation failed: {form.errors}")
            return JsonResponse({"success": False, "errors": form.errors.as_json()}, status=400)
    else:
        logger.info("Rendering profile form")
        return render(request, "account_profile.html", {"form": UserEditForm(instance=request.user)})
            

def manage_address(request):
    addresses = Address.objects.filter(user=request.user)
    response = render(request, 'manage_address.html', {'addresses': addresses})
    
    # Add cache control headers to prevent caching
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = '0'
    response['X-Content-Type-Options'] = 'nosniff'
    return response

def add_address(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        city = request.POST.get('city') 
        district = request.POST.get('district')
        state = request.POST.get('state')
        pincode = request.POST.get('pincode')
        phone = request.POST.get('phone')
        landmark = request.POST.get('landmark', '')
        alternative_phone = request.POST.get('alternative_phone', '')

        if not all([name, city, district, state, pincode, phone]):
            return JsonResponse({
                'success': False,
                'message': 'All required fields must be filled.'
            }, status=400)

        address = Address(
            user=request.user,
            name=name,
            city=city,
            district=district,
            state=state,
            pincode=pincode,
            phone=phone,
            landmark=landmark,
            alternative_phone=alternative_phone
        )
        address.save()
        return JsonResponse({
            'success': True,
            'address': {
                'id': address.id,
                'name': address.name,
                'city': address.city,
                'district': address.district,
                'state': address.state,
                'pincode': address.pincode,
                'phone': address.phone,
                'landmark': address.landmark or '',
                'alternative_phone': address.alternative_phone or ''
            },
            'message': 'Address added successfully!'
        })

    return render(request, 'add_address.html')


def edit_address(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user) 

    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            return redirect('manage_address')  
    else:
        form = AddressForm(instance=address)

    return render(request, 'edit_address.html', {'form': form})

@require_POST
@login_required
def delete_address(request, pk):
    try:
        address = get_object_or_404(Address, pk=pk, user=request.user)
        logger.info(f"Deleting address {pk} for user {request.user.username}")
        address.delete()
        logger.info(f"Address {pk} deleted successfully")
        
        response = JsonResponse({'success': True})
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response
        
    except Address.DoesNotExist:
        logger.error(f"Address {pk} not found or user {request.user.username} does not have permission")
        return JsonResponse({'success': False, 'message': 'Address not found or you do not have permission to delete it'}, status=404)
    except Exception as e:
        logger.error(f"Error deleting address {pk}: {str(e)}")
        return JsonResponse({'success': False, 'message': f'Error deleting address: {str(e)}'}, status=500)

def add_to_cart(request, product_id):
    if not request.user.is_authenticated:
        return JsonResponse({
            'success': False, 
            'message': 'Please login to add items to cart',
            'login_required': True
        })
    
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        product = get_object_or_404(Product, id=product_id)
        
        # Get variant_id from POST data
        variant_id = request.POST.get('variant_id')
        if not variant_id:
            return JsonResponse({
                'success': False, 
                'message': 'Product variant not specified'
            })
        
        try:
            variant = Variant.objects.get(id=variant_id, product=product)
            logger.info(f"Variant found for add_to_cart: {variant_id}")
        except Variant.DoesNotExist:
            logger.error(f"Variant not found: {variant_id}")
            return JsonResponse({
                'success': False, 
                'message': 'Invalid product variant'
            })

        # Check product availability
        if not product.status or product.is_deleted or not product.category.status:
            logger.warning(f"Product {product.id} is unavailable")
            return JsonResponse({
                'success': False, 
                'message': 'This product is unavailable.'
            })
        
        # Check stock
        if variant.stock <= 0:
            logger.warning(f"Variant {variant_id} out of stock")
            return JsonResponse({
                'success': False, 
                'message': 'This product is out of stock.'
            })
        
        # Get wishlist_id from POST data
        wishlist_id = request.POST.get('wishlist_id')
        
        # Create or update cart item
        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            product=product,
            variant=variant,
            defaults={'quantity': 1}
        )
        
        # Remove from wishlist if applicable
        if wishlist_id:
            Wishlist.objects.filter(id=wishlist_id, user=request.user).delete()
            logger.info(f"Removed wishlist item {wishlist_id} during add_to_cart")
        else:
            Wishlist.objects.filter(user=request.user, product=product, variant=variant).delete()
            logger.info(f"Removed wishlist item for product {product_id} and variant {variant_id} during add_to_cart")
        
        # Prepare response data
        response_data = {
            'success': True,
            'cart_count': Cart.objects.filter(user=request.user).count(),
            'wishlist_count': Wishlist.objects.filter(user=request.user).count()
        }
        
        if not created:
            if cart_item.quantity < variant.stock:
                cart_item.quantity += 1
                cart_item.save()
                response_data['message'] = f"{product.name} quantity increased in cart!"
                response_data['current_quantity'] = cart_item.quantity
            else:
                response_data.update({
                    'success': False,
                    'message': 'Cannot add more, stock limit reached.'
                })
        else:
            response_data['message'] = f"{product.name} added to cart!"
            response_data['is_new_item'] = True
        
        logger.info(f"add_to_cart response: {response_data}")
        return JsonResponse(response_data)

    logger.error("Invalid request for add_to_cart")
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def get_default_variant(request, product_id):
    """Get the first available variant for a product."""
    if request.headers.get('X-Requested-With') != 'XMLHttpRequest':
        return redirect('home')
        
    try:
        product = get_object_or_404(Product, id=product_id)
        
        # Check if product is available
        if not product.status or product.is_deleted or not product.category.status:
            return JsonResponse({
                'success': False, 
                'message': 'This product is unavailable.'
            })
            
        # Get first variant with stock
        variant = product.variants.filter(stock__gt=0).first()
        
        if variant:
            return JsonResponse({
                'success': True,
                'variant_id': variant.id,
                'message': 'Default variant found.'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'This product is out of stock.'
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'Error getting product variant.',
            'error': str(e)
        })
    
import logging
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import utils as django_utils
import time

logger = logging.getLogger(__name__)

@login_required
@require_POST
def add_to_cart_with_variant(request, variant_id):
    if request.method == 'POST' and request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        max_retries = 3
        retry_count = 0
        retry_delay = 0.5
        
        while retry_count < max_retries:
            try:
                logger.info(f"Add to cart request from {request.user} for variant {variant_id}")
                variant = Variant.objects.select_related('product', 'product__category').get(id=variant_id)
                
                if not variant.product.status or not variant.product.category.status:
                    logger.warning(f"Product {variant.product.id} is unavailable")
                    return JsonResponse({
                        'success': False,
                        'message': 'This product is currently unavailable',
                        'status': 'unavailable'
                    }, status=400)
                
                if variant.stock <= 0:
                    logger.warning(f"Variant {variant_id} out of stock")
                    return JsonResponse({
                        'success': False,
                        'message': 'This product is out of stock',
                        'status': 'out_of_stock',
                        'stock': 0
                    }, status=400)
                
                with transaction.atomic():
                    cart_item, created = Cart.objects.get_or_create(
                        user=request.user,
                        variant=variant,
                        defaults={'quantity': 1, 'product': variant.product}
                    )
                    
                    if not created:
                        if cart_item.quantity >= variant.stock:
                            logger.warning(f"Stock limit reached for variant {variant_id}")
                            return JsonResponse({
                                'success': False,
                                'message': 'Cannot add more items. Stock limit reached.',
                                'status': 'max_quantity',
                                'stock': variant.stock,
                                'current_quantity': cart_item.quantity
                            }, status=400)
                        
                        cart_item.quantity += 1
                        cart_item.save()
                    
                    # Remove the item from the wishlist if it exists
                    Wishlist.objects.filter(user=request.user, product=variant.product, variant=variant).delete()
                    logger.info(f"Removed wishlist item for product {variant.product.id} and variant {variant_id} during add_to_cart_with_variant")

                    logger.info(f"Cart updated for {request.user}. New quantity: {cart_item.quantity}. New stock: {variant.stock}")
                    
                    return JsonResponse({
                        'success': True,
                        'message': 'Added to cart successfully!',
                        'stock': variant.stock,
                        'current_quantity': cart_item.quantity,
                        'cart_count': Cart.objects.filter(user=request.user).count(),
                        'wishlist_count': Wishlist.objects.filter(user=request.user).count(),  # Added
                        'is_new_item': created
                    })
                    
            except Variant.DoesNotExist:
                logger.error(f"Variant {variant_id} not found")
                return JsonResponse({
                    'success': False,
                    'message': 'Product variant not found',
                    'status': 'not_found'
                }, status=404)
                
            except django_utils.OperationalError as e:
                if 'database is locked' in str(e) and retry_count < max_retries - 1:
                    logger.warning(f"Database locked, retrying ({retry_count + 1}/{max_retries})...")
                    retry_count += 1
                    time.sleep(retry_delay * (2 ** retry_count))
                    continue
                else:
                    logger.error(f"Database error in add_to_cart after {retry_count} retries: {str(e)}", exc_info=True)
                    return JsonResponse({
                        'success': False,
                        'message': 'The system is currently busy. Please try again.',
                        'status': 'db_locked'
                    }, status=503)
                    
            except Exception as e:
                logger.error(f"Error in add_to_cart: {str(e)}", exc_info=True)
                return JsonResponse({
                    'success': False,
                    'message': 'An error occurred. Please try again.',
                    'status': 'error'
                }, status=500)
            break
            
        if retry_count >= max_retries:
            logger.error(f"Failed to add to cart after {max_retries} retries")
            return JsonResponse({
                'success': False,
                'message': 'The system is currently busy. Please try again later.',
                'status': 'max_retries'
            }, status=503)
        
    return JsonResponse({
        'success': False,
        'message': 'Invalid request',
        'status': 'invalid_request'
    }, status=400)

    
@require_POST
@login_required
def update_cart_quantity(request, variant_id, action):
    try:
        cart_item = get_object_or_404(Cart, user=request.user, variant_id=variant_id)
        variant = cart_item.variant
        product = cart_item.variant.product

        # Check if product is inactive
        if not product.status:
            return JsonResponse({
                'success': False,
                'message': f'The product {product.name} is currently unavailable.',
                'stock': variant.stock
            }, status=400)
        
        if action == 'increase':
            if cart_item.quantity >= variant.stock:
                return JsonResponse({
                    'success': False,
                    'message': 'Cannot add more {product.name}. Stock limit reached.',
                    'stock': variant.stock
                }, status=400)
            
            cart_item.quantity += 1
            cart_item.save()
            
        elif action == 'decrease':
            if cart_item.quantity <= 1:
                cart_item.delete()
            else:
                cart_item.quantity -= 1
                cart_item.save()
        
        # Recalculate totals with discounts
        cart_items = Cart.objects.filter(user=request.user)
        current_time = timezone.now()
        subtotal = Decimal('0.00')

        # Calculate subtotal considering discounts
        for item in cart_items:
            product = item.variant.product
            original_price = item.variant.price
            
            # Find applicable offers
            applicable_offers = Offer.objects.filter(
                models.Q(product=product) | models.Q(category=product.category),
                status=True,
                start_date__lte=current_time,
                end_date__gte=current_time
            )

            # Calculate maximum discount
            max_discount = Decimal('0.00')
            for offer in applicable_offers:
                if offer.offer_type == 'PERCENTAGE':
                    discount = (offer.discount / Decimal('100')) * original_price
                else:  # FIXED amount
                    discount = offer.discount
                
                if discount > max_discount:
                    max_discount = discount
            
            # Use discounted price if offer exists
            item_price = original_price - max_discount if max_discount > 0 else original_price
            subtotal += item.quantity * item_price

        delivery_charge = Decimal('0.00')
        total_price = subtotal + delivery_charge
        
        return JsonResponse({
            'success': True,
            'quantity': cart_item.quantity if cart_item.quantity > 0 else 0,
            'subtotal': str(subtotal),
            'delivery_charge': str(delivery_charge),
            'total_price': str(total_price),
            'cart_count': cart_items.count(),
            'stock': variant.stock,
            'message': 'Quantity updated successfully'
        })
        
    except Exception as e:
        logger.error(f"Error in update_cart_quantity: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': str(e),
            'stock': variant.stock if 'variant' in locals() else 0
        }, status=400)

@login_required
def cart_view(request):
    cart_items = Cart.objects.filter(user=request.user).select_related('variant__product', 'variant__product__category')
    current_time = timezone.now()
    
    # Process each cart item to calculate discounts
    enhanced_cart_items = []
    subtotal = Decimal('0.00')
    has_inactive_products = False
    
    for item in cart_items:
        original_price = item.variant.price
        quantity = item.quantity
        product = item.variant.product
        
        # Find all applicable offers (both product and category)
        applicable_offers = Offer.objects.filter(
            models.Q(product=product) | models.Q(category=product.category),
            status=True,
            start_date__lte=current_time,
            end_date__gte=current_time
        )
        
        # Calculate maximum discount from all applicable offers
        max_discount = Decimal('0.00')
        for offer in applicable_offers:
            if offer.offer_type == 'PERCENTAGE':
                discount = (offer.discount / Decimal('100')) * original_price
            else:  # FIXED amount
                discount = offer.discount
            
            if discount > max_discount:
                max_discount = discount
        
        # Calculate final price after discount
        discounted_price = max(original_price - max_discount, Decimal('0.00'))
        has_offer = max_discount > 0

        # Check if product is inactive
        is_product_inactive = not product.status
        
        # Add to enhanced cart items
        enhanced_cart_items.append({
            'cart_item': item,  # Original cart item
            'original_price': original_price,
            'discounted_price': discounted_price,
            'has_offer': has_offer,
            'max_discount': max_discount,
            'is_product_inactive': is_product_inactive
        })
        
        # Update subtotal using discounted price if available, otherwise use original price
        item_price = discounted_price if has_offer else original_price
        subtotal += quantity * item_price

        # Update has_inactive_products flag
        if is_product_inactive:
            has_inactive_products = True
    
    delivery_charge = Decimal('0.00')
    total_price = subtotal + delivery_charge
    out_of_stock = any(item['cart_item'].variant.stock < item['cart_item'].quantity for item in enhanced_cart_items)
    
    return render(request, 'cart.html', {
        'cart_items': cart_items,  # Keep original for compatibility
        'enhanced_cart_items': enhanced_cart_items,  # New structure
        'subtotal': subtotal,
        'delivery_charge': delivery_charge,
        'total_price': total_price,
        'out_of_stock': out_of_stock,
        'has_inactive_products': has_inactive_products
    })

@require_POST
@login_required
def remove_from_cart(request, variant_id):
    try:
        cart_item = Cart.objects.filter(user=request.user, variant_id=variant_id).first()
        
        if not cart_item:
            return JsonResponse({
                'success': False,
                'message': 'Cart item not found.'
            }, status=404)
        
        product_name = cart_item.variant.product.name
        cart_item.delete()
        
        remaining_cart_items = Cart.objects.filter(user=request.user)
        current_time = timezone.now()
        subtotal = Decimal('0.00')
        
        for item in remaining_cart_items:
            product = item.variant.product
            original_price = item.variant.price
            
            applicable_offers = Offer.objects.filter(
                models.Q(product=product) | models.Q(category=product.category),
                status=True,
                start_date__lte=current_time,
                end_date__gte=current_time
            )

            max_discount = Decimal('0.00')
            for offer in applicable_offers:
                if offer.offer_type == 'PERCENTAGE':
                    discount = (offer.discount / Decimal('100')) * original_price
                else:
                    discount = offer.discount
                max_discount = max(max_discount, discount)
            
            item_price = original_price - max_discount
            subtotal += item.quantity * item_price

        delivery_charge = Decimal('0.00')
        total_price = subtotal + delivery_charge
        cart_count = remaining_cart_items.count()

        response_data = {
            'success': True,
            'subtotal': str(subtotal),
            'delivery_charge': str(delivery_charge),
            'total_price': str(total_price),
            'cart_count': cart_count,
            'message': f"{product_name} (variant) removed from cart."
        }
        logger.info(f"Remove from cart response: {response_data}")  # Updated to use logger
        return JsonResponse(response_data)
    except Exception as e:
        logger.error(f"Error removing cart item: {str(e)}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': str(e)
        }, status=400)

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)

def checkout(request):
    try:
        # Ensure user is authenticated
        if not request.user.is_authenticated:
            messages.error(request, "Please log in to proceed to checkout.")
            return redirect('login')

        cart_items = Cart.objects.filter(user=request.user)
        
        # Log debug information
        logger.debug(f"Cart items count: {cart_items.count()}")
        
        # Check if cart is empty
        if not cart_items.exists():
            messages.warning(request, "Your cart is empty.")
            return redirect('cart')

        # Check for out-of-stock items
        out_of_stock_items = []
        inactive_products = []
        for item in cart_items:
            if item.quantity > item.variant.stock:
                out_of_stock_items.append(item.variant.product.name)
                messages.error(request, f"{item.variant.product.name} has insufficient stock.")
            if not item.variant.product.status:
                inactive_products.append(item.variant.product.name)
                messages.error(request, f"{item.variant.product.name} is currently unavailable.")

        if out_of_stock_items or inactive_products:
            logger.debug(f"Checkout blocked: Out of stock: {out_of_stock_items}, Inactive: {inactive_products}")
            return redirect('cart')

        # Calculate subtotal, discounts, and total price
        subtotal = 0
        total_discount = 0
        cart_items_with_offers = []
        current_time = timezone.now()

        for item in cart_items:
            original_price = item.variant.price
            quantity = item.quantity

            # Find all applicable offers (both product-specific and category-wide)
            applicable_offers = Offer.objects.filter(
                models.Q(product=item.product) | models.Q(category=item.product.category),
                status=True,
                start_date__lte=current_time,
                end_date__gte=current_time
            )

            # Calculate the maximum discount from all applicable offers
            max_discount = Decimal('0.00')
            for offer in applicable_offers:
                if offer.offer_type == 'PERCENTAGE':
                    discount = (offer.discount / Decimal('100')) * original_price
                else:  # FIXED amount
                    discount = offer.discount
                
                if discount > max_discount:
                    max_discount = discount

            # Ensure discount doesn't make price negative
            discounted_price = max(original_price - max_discount, Decimal('0.00'))
            item_total = quantity * original_price
            item_discounted_total = quantity * discounted_price
            
            subtotal += item_total
            total_discount += (item_total - item_discounted_total)

            # Add offer details to cart item for template
            cart_items_with_offers.append({
                'item': item,
                'original_price': original_price,
                'discounted_price': discounted_price,
                'offer_discount': max_discount,
                'item_total': item_total,
                'item_discounted_total': item_discounted_total,
                'has_offer': max_discount > 0
            })

        delivery_charge = 0 if subtotal > 0 else 0
        total_price = (subtotal - total_discount) + delivery_charge

        cod_allowed = total_price <= Decimal('1000.00')

        addresses = Address.objects.filter(user=request.user)
        
        # Get wallet balance
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        wallet_balance = wallet.balance

        context = {
            'cart_items': cart_items_with_offers,
            'subtotal': subtotal,
            'total_discount': total_discount,
            'delivery_charge': delivery_charge,
            'total_price': total_price,
            'addresses': addresses,
            'razorpay_key_id': settings.RAZORPAY_KEY_ID,
            'wallet_balance': wallet_balance,
            'cod_allowed': cod_allowed,
        }   
        return render(request, 'checkout.html', context)

    except Exception as e:
        logger.error(f"Error in checkout view: {str(e)}", exc_info=True)
        messages.error(request, "An unexpected error occurred. Please try again.")
        return redirect('cart')

@login_required
@csrf_exempt
def get_available_coupons(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        cart_total = Decimal(data.get('cart_total', 0))
        
        # Get all valid coupons
        coupons = Coupon.objects.filter(
            is_active=True,
            valid_from__lte=timezone.now(),
            valid_until__gte=timezone.now()
        )
        
        available_coupons = []
        for coupon in coupons:
            is_valid, message = coupon.is_valid(user=request.user, cart_total=cart_total)
            if is_valid:
                available_coupons.append({
                    'code': coupon.code,
                    'discount_type': coupon.discount_type,
                    'discount_value': float(coupon.discount_value),
                    'min_purchase_amount': float(coupon.min_purchase_amount),
                    'max_discount_amount': float(coupon.max_discount_amount) if coupon.max_discount_amount else None,
                    'valid_until': coupon.valid_until.isoformat(),
                })
        
        return JsonResponse({'coupons': available_coupons})
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)

@login_required
@csrf_exempt
def apply_coupon(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        coupon_code = data.get('coupon_code')
        cart_total = Decimal(data.get('cart_total', 0))
        
        try:
            coupon = Coupon.objects.get(code=coupon_code, is_active=True)
            is_valid, message = coupon.is_valid(user=request.user, cart_total=cart_total)
            
            if is_valid:
                discount_amount = coupon.calculate_discount(cart_total)
                return JsonResponse({
                    'success': True,
                    'discount_amount': float(discount_amount),
                })
            else:
                return JsonResponse({
                    'success': False,
                    'message': message,
                })
        except Coupon.DoesNotExist:
            return JsonResponse({
                'success': False,
                'message': 'Invalid coupon code',
            })
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)

@csrf_exempt
def create_razorpay_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            amount = data.get('amount')
            
            # Better validation and logging
            logger.debug(f"Received amount: {amount}")
            
            if not amount:
                logger.error("No amount provided in request")
                return JsonResponse({'error': 'Amount is required'}, status=400)
            
            try:
                amount = int(amount)  # Ensure amount is an integer
                if amount <= 0:
                    logger.error(f"Invalid amount: {amount}")
                    return JsonResponse({'error': 'Amount must be greater than 0'}, status=400)
            except (ValueError, TypeError):
                logger.error(f"Amount is not a valid number: {amount}")
                return JsonResponse({'error': 'Invalid amount format'}, status=400)
            
            logger.debug(f"Creating Razorpay order for amount: {amount}")
            order = razorpay_client.order.create({
                'amount': amount,
                'currency': 'INR',
                'payment_capture': 1
            })
            
            logger.debug(f"Razorpay order created: {order['id']}")
            return JsonResponse({
                'order_id': order['id'],
                'amount': order['amount'],
                'currency': order['currency'],
                'key': settings.RAZORPAY_KEY_ID
            })
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {str(e)}")
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        except Exception as e:
            logger.error(f"Error creating Razorpay order: {str(e)}", exc_info=True)
            return JsonResponse({'error': f'Unexpected error: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)

# Update this function in your views.py
@csrf_exempt
def verify_payment(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            params_dict = {
                'razorpay_payment_id': data.get('razorpay_payment_id'),
                'razorpay_order_id': data.get('razorpay_order_id'),
                'razorpay_signature': data.get('razorpay_signature')
            }
            
            # Improved logging and validation
            logger.debug(f"Verifying payment with params: {params_dict}")
            
            # Check for missing parameters
            missing_params = [k for k, v in params_dict.items() if not v]
            if missing_params:
                logger.error(f"Missing payment parameters: {missing_params}")
                return JsonResponse({
                    'status': 'failure', 
                    'error': f"Missing required payment parameters: {', '.join(missing_params)}"
                }, status=400)
            
            # Verify the payment signature
            try:
                razorpay_client.utility.verify_payment_signature(params_dict)
                logger.debug("Payment signature verified successfully")
                return JsonResponse({'status': 'success'})
            except razorpay.errors.SignatureVerificationError as sve:
                logger.error(f"Signature verification failed: {str(sve)}", exc_info=True)
                return JsonResponse({'status': 'failure', 'error': 'Payment signature verification failed'}, status=400)
                
        except json.JSONDecodeError as jde:
            logger.error(f"Invalid JSON in request: {str(jde)}", exc_info=True)
            return JsonResponse({'status': 'failure', 'error': 'Invalid request format'}, status=400)
        except Exception as e:
            logger.error(f"Unexpected error in verify_payment: {str(e)}", exc_info=True)
            return JsonResponse({'status': 'failure', 'error': 'An unexpected error occurred'}, status=500)
        
@login_required
def get_wallet_balance(request):
    try:
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        return JsonResponse({'balance': float(wallet.balance)})
    except Wallet.DoesNotExist:
        logger.error("Wallet does not exist for user: %s", request.user)
        return JsonResponse({'balance': 0.00}, status=200)
    except Exception as e:
        logger.error(f"Error fetching wallet balance for user {request.user}: {str(e)}", exc_info=True)
        return JsonResponse({'error': 'Unable to fetch wallet balance'}, status=500)
    
@login_required
@csrf_exempt
def create_razorpay_wallet_order(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            amount = int(data.get('amount'))  # Amount in paise

            if amount <= 0:
                return JsonResponse({'error': 'Invalid amount'}, status=400)

            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            order_data = {
                'amount': amount,
                'currency': 'INR',
                'payment_capture': '1'
            }
            order = client.order.create(data=order_data)

            return JsonResponse({
                'order_id': order['id'],
                'amount': amount,
                'currency': 'INR',
                'key': settings.RAZORPAY_KEY_ID
            })
        except Exception as e:
            logger.error(f"Error creating Razorpay wallet order: {str(e)}")
            return JsonResponse({'error': 'Unable to create payment order'}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)

@login_required
@csrf_exempt
def verify_wallet_payment(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)
            payment_id = data.get('razorpay_payment_id')
            order_id = data.get('razorpay_order_id')
            signature = data.get('razorpay_signature')
            amount = Decimal(data.get('amount'))  # Amount in rupees

            # Verify signature
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            params_dict = {
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': order_id,
                'razorpay_signature': signature
            }
            client.utility.verify_payment_signature(params_dict)

            # Update wallet balance
            with transaction.atomic():
                wallet = Wallet.objects.get(user=request.user)
                wallet.add_funds(
                    amount=amount,
                    description=f"Added ₹{amount} via Razorpay (Payment ID: {payment_id})"
                )

            return JsonResponse({'status': 'success'})
        except razorpay.errors.SignatureVerificationError:
            logger.error("Razorpay signature verification failed")
            return JsonResponse({'error': 'Invalid payment signature'}, status=400)
        except Exception as e:
            logger.error(f"Error verifying wallet payment: {str(e)}")
            return JsonResponse({'error': 'Payment verification failed'}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)
        
# views.py (user side)
import logging
import json
from django.http import JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

@csrf_exempt
@login_required
def place_order(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            payment_method = data.get('payment_method')
            shipping_address_id = data.get('shipping_address')
            coupon_code = data.get('coupon_code')  
            razorpay_payment_id = data.get('razorpay_payment_id')
            razorpay_order_id = data.get('razorpay_order_id')
            total_price = data.get('total_price')

            if not payment_method or not shipping_address_id:
                return JsonResponse({'success': False, 'message': 'Invalid data'}, status=400)

            if payment_method.upper() == 'COD' and Decimal(str(total_price)) > Decimal('1000.00'):
                return JsonResponse({
                    'success': False,
                    'message': 'Cash on Delivery is not available for orders above ₹1000.'
                }, status=400)
            
            user = request.user
            address = Address.objects.get(id=shipping_address_id, user=user)
            cart_items = Cart.objects.filter(user=user)
            
            if not cart_items.exists():
                return JsonResponse({'success': False, 'message': 'Cart is empty'}, status=400)

            # Detailed stock checking
            insufficient_stock_items = []
            
            # First pass: Check stock availability
            for cart_item in cart_items:
                variant = cart_item.variant
                logger.info(f"Stock Check: {variant} - Requested: {cart_item.quantity}, Available: {variant.stock}")
                
                if cart_item.quantity > variant.stock:
                    insufficient_stock_items.append({
                        'name': f"{variant.product.name} ({variant.ram}GB/{variant.storage}GB/{variant.color})",
                        'requested': cart_item.quantity,
                        'available': variant.stock
                    })

            # If any items have insufficient stock, return detailed error
            if insufficient_stock_items:
                return JsonResponse({
                    'success': False,
                    'message': 'Insufficient stock',
                    'details': insufficient_stock_items
                }, status=400)

            with transaction.atomic():
                # Calculate total price
                subtotal = 0
                total_discount = 0
                
                # Create order
                order = Order.objects.create(
                    user=user,
                    shipping_address=address,
                    payment_method=payment_method.upper(),
                    total_price=Decimal(str(total_price)) if total_price else Decimal('0.00'),
                    shipping_fee=0,
                    razorpay_payment_id=razorpay_payment_id if payment_method.upper() == 'RAZORPAY' else None,
                    razorpay_order_id=razorpay_order_id if payment_method.upper() == 'RAZORPAY' else None,
                    payment_status='Success' if payment_method.upper() == 'RAZORPAY' else 'Pending'
                )
                
                # Process each cart item
                for cart_item in cart_items:
                    variant = cart_item.variant
                    original_price = variant.price
                    offer_discount = Offer().get_total_offer(cart_item.product)  # Get max offer discount
                    discounted_price = max(original_price - offer_discount, Decimal('0.00'))  # Ensure price doesn't go negative

                    # Calculate totals
                    item_subtotal = cart_item.quantity * original_price
                    item_discounted_total = cart_item.quantity * discounted_price
                    
                    subtotal += item_subtotal
                    total_discount += (item_subtotal - item_discounted_total)
                    
                    # Create order item
                    OrderItem.objects.create(
                        order=order,
                        product=cart_item.product,
                        variant=variant,
                        quantity=cart_item.quantity,
                        price=discounted_price
                    )
                    
                    # Reduce variant stock
                    variant.stock -= cart_item.quantity
                    variant.save(update_fields=['stock'])

                # Apply coupon discount if provided
                coupon_discount = Decimal('0.00')
                if coupon_code:
                    try:
                        coupon = Coupon.objects.get(code=coupon_code, is_active=True)
                        is_valid, message = coupon.is_valid(user=user, cart_total=subtotal - total_discount)
                        if is_valid:
                            coupon_discount = coupon.calculate_discount(subtotal - total_discount)
                            coupon.usage_count += 1
                            coupon.save()
                            CouponUsage.objects.create(
                                coupon=coupon,
                                user=user,
                                order=order,
                                discount_amount=coupon_discount
                            )
                        else:
                            return JsonResponse({'success': False, 'message': message}, status=400)
                    except Coupon.DoesNotExist:
                        pass

                # Update order total price (subtotal - discount + shipping_fee)
                final_total = (subtotal - total_discount - coupon_discount) + order.shipping_fee
                order.total_price = final_total
                order.save(update_fields=['total_price'])
                
                # Handle wallet payment
                if payment_method.upper() == 'WALLET':
                    wallet, created = Wallet.objects.get_or_create(user=user)
                    if wallet.balance < final_total:
                        return JsonResponse({
                            'success': False,
                            'message': 'Insufficient wallet balance. Please add funds to your wallet.'
                        }, status=400)
                    wallet.deduct_funds(
                        amount=final_total,
                        order=order
                    )
                    order.payment_status = 'Success'
                    order.save(update_fields=['payment_status'])
                
                # Clear the cart
                cart_items.delete()

            return JsonResponse({
                'success': True,
                'order_id': order.id
            })
        
        except Address.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Invalid shipping address'}, status=400)
        except Wallet.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Wallet not found'}, status=400)
        except Exception as e:
            logger.error(f"Order placement error: {str(e)}", exc_info=True)
            return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=400)


def order_success(request, order_id):
    """Display the order success page after a successful order placement."""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    
    context = {
        'order_id': order.id,
        'order': order,
        'message': f'Your order #{order.id} has been placed successfully!',
        'total_price': order.total_price,
        'payment_method': order.payment_method,
        'shipping_address': order.shipping_address, 
        'order_items': order.items.all()
    }
    
    return render(request, 'order_success.html', context)

@login_required
@never_cache
def order_details(request):
    user_orders = Order.objects.filter(user=request.user).order_by('-created_at')

    paginator = Paginator(user_orders, 5)  
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    print(f"User orders fetched at {timezone.now()}: {[(o.id, o.status) for o in page_obj]}")
    return render(request, 'order_details.html', {'page_obj': page_obj})

@login_required
def get_order_statuses(request):
    orders = Order.objects.filter(user=request.user).values('id', 'status')
    statuses = {str(order['id']): order['status'] for order in orders}
    return JsonResponse({'success': True, 'statuses': statuses})

@login_required
@never_cache
def order_fulldetail_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    order_items = OrderItem.objects.filter(order=order).select_related('product', 'variant')
    grand_total = order.calculate_total_price()
    
    # Determine if return is allowed (within 7 days of delivery and not returned)
    from django.utils import timezone
    can_return = order.status == 'Delivered' and (
        timezone.now() - order.created_at
    ).days <= 7  # Example: 7-day return policy
    
    print(f"Order #{order_id} details fetched at {timezone.now()}: "
          f"Status={order.status}, Grand Total={grand_total}, "
          f"Items={[(item.product.name, item.quantity, item.price, item.is_returned) for item in order_items]}, "
          f"Can Return={can_return}")
    
    return render(request, 'order_fulldetail.html', {
        'order': order,
        'order_items': order_items,
        'grand_total': grand_total,
        'can_return': can_return
    })

def generate_invoice_pdf(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id)
        total_price = order.calculate_total_price()
        shipping_fee = order.shipping_fee
        subtotal = total_price - shipping_fee

        # Create the HttpResponse object with PDF headers
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Invoice_Order_{order_id}.pdf"'

        # Create the PDF object
        doc = SimpleDocTemplate(response, pagesize=letter, rightMargin=50, leftMargin=50, topMargin=50, bottomMargin=50)
        elements = []

        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name='Title',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=1,  # Center alignment
            spaceAfter=12,
        )
        header_style = ParagraphStyle(
            name='Header',
            parent=styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
        )
        normal_style = styles['BodyText']

        # Add title
        elements.append(Paragraph("Phonix - Order Invoice", title_style))
        logger.debug(f"Added title for Order #{order_id}")

        # Add order details
        elements.append(Paragraph(f"Order ID: #{order.id}", header_style))
        elements.append(Paragraph(f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
        elements.append(Paragraph(f"Status: {order.status}", normal_style))
        elements.append(Spacer(1, 20))

        # Add order items table
        table_data = [["Image", "Product", "Quantity", "Price"]]
        for item in order.items.all():
            product_name = item.product.name if len(item.product.name) <= 40 else item.product.name[:37] + "..."
            
            # Safely handle product image
            img = None
            try:
                if item.variant and item.variant.images.exists():
                    product_image = item.variant.images.first()  # Use variant images instead of product
                    image_path = product_image.image.path
                    logger.debug(f"Checking image for {product_name}, Path: {image_path}")
                    if os.path.exists(image_path):
                        img = ReportLabImage(image_path, width=50, height=50)
                        logger.debug(f"Image exists for {product_name} at {image_path}")
                    else:
                        logger.warning(f"Image file missing for {product_name} at {image_path}")
                        img = Paragraph("No Image", normal_style)
                else:
                    logger.debug(f"No images for {product_name} or variant {item.variant}")
                    img = Paragraph("No Image", normal_style)
            except Exception as e:
                logger.error(f"Error processing image for {product_name}: {str(e)}")
                img = Paragraph("Image Error", normal_style)

            # Ensure price is valid
            price = item.price if item.price is not None else 0.00
            table_data.append([img, product_name, str(item.quantity), f"₹{price:.2f}"])

        # Create the table
        table = Table(table_data, colWidths=[60, 240, 80, 80])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 20))

        # Add order summary
        elements.append(Paragraph("Order Summary", header_style))
        elements.append(Paragraph(f"Subtotal: ₹{subtotal:.2f}", normal_style))
        elements.append(Paragraph(f"Shipping Fee: ₹{shipping_fee:.2f}", normal_style))
        elements.append(Paragraph(f"Grand Total: ₹{total_price:.2f}", header_style))

        # Add footer
        elements.append(Spacer(1, 40))
        elements.append(Paragraph("Thank you for shopping with Phonix!", normal_style))

        # Build the PDF
        logger.debug(f"Building PDF with {len(elements)} elements for Order #{order_id}")
        doc.build(elements)
        logger.info(f"Successfully generated PDF for Order #{order_id}")
        return response

    except Exception as e:
        logger.error(f"Failed to generate PDF for Order #{order_id}: {str(e)}", exc_info=True)
        # Return a simple error PDF instead of raising a 500 error
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Error_Invoice_Order_{order_id}.pdf"'
        doc = SimpleDocTemplate(response, pagesize=letter)
        elements = [Paragraph(f"Error generating invoice: {str(e)}", getSampleStyleSheet()['BodyText'])]
        doc.build(elements)
        return response
    
def is_admin(user):
    return user.is_staff or user.is_superuser           

@login_required
@csrf_protect
def cancel_order(request, order_id):
    if request.method == "POST":
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.status in ["Pending", "Confirmed", "Shipped"]:
            try:
                with transaction.atomic():
                    order.status = "Cancelled"
                    order.save()
                    stock_updates = {}
                    for item in order.items.all():
                        # Check if the OrderItem has a Variant
                        if item.variant:
                            variant = item.variant
                            print(f"Before increment - Variant: {variant}, Stock: {variant.stock}, Item Quantity: {item.quantity}")
                            variant.stock += item.quantity  # Increment variant stock
                            print(f"After increment (pre-save) - Variant: {variant}, Stock: {variant.stock}")
                            variant.save() 
                            variant.refresh_from_db()  
                            print(f"After save - Variant: {variant}, Stock: {variant.stock}")
                            stock_updates[variant.id] = variant.stock
                        else:
                            product = item.product
                            print(f"Before increment - Product: {product.name}, Stock: {product.stock}, Item Quantity: {item.quantity}")
                            product.stock += item.quantity
                            print(f"After increment (pre-save) - Product: {product.name}, Stock: {product.stock}")
                            product.save()
                            product.refresh_from_db()
                            print(f"After save - Product: {product.name}, Stock: {product.stock}")
                            stock_updates[product.id] = product.stock
                    # Refund logic for online payments
                    if order.payment_method in ['Razorpay', 'Wallet'] and order.payment_status == 'Success':
                        wallet, created = Wallet.objects.get_or_create(user=request.user)
                        refund_amount = order.total_price
                        wallet.add_funds(
                            amount=refund_amount,
                            description=f"Refund for cancelled order #{order.id}",
                            order=order
                        )
                        print(f"Refunded ₹{refund_amount} to wallet for cancelled order #{order.id}")

                    return JsonResponse({
                        "success": True,
                        "message": "Order cancelled successfully!",
                        "stock_updates": stock_updates
                    })
            except Exception as e:
                print(f"Transaction error: {e}")
                return JsonResponse({"success": False, "message": f"Transaction failed: {str(e)}"}, status=500)
        return JsonResponse({"success": False, "message": "Order cannot be cancelled!"}, status=400)

    return JsonResponse({"success": False, "message": "Invalid request!"}, status=400)


@login_required
@require_POST
def return_order(request, order_id):
    try:
        order = get_object_or_404(Order, id=order_id, user=request.user)
        if order.status != "Delivered":
            return JsonResponse({
                "success": False,
                "message": "Only delivered orders can be returned."
            })
        
        # Check return window (e.g., 7 days)
        if (timezone.now() - order.created_at).days > 7:
            return JsonResponse({
                "success": False,
                "message": "Return period has expired (7 days)."
            })
        
        data = json.loads(request.body)
        item_id = data.get('item_id')
        reason = data.get('reason', '').strip()
        
        if not reason:
            return JsonResponse({
                "success": False,
                "message": "Please provide a reason for the return."
            })
        
        with transaction.atomic():
            order_item = get_object_or_404(OrderItem, id=item_id, order=order)
            if order_item.is_returned:
                return JsonResponse({
                    "success": False,
                    "message": "This item has already been returned."
                })
            
            order_item.is_returned = True
            order_item.return_reason = reason
            order_item.save()
            
            # Increment stock
            if order_item.variant:
                order_item.variant.stock += order_item.quantity
                order_item.variant.save()
                order_item.variant.refresh_from_db()
                print(f"Incremented stock for {order_item.variant} by {order_item.quantity}. New stock: {order_item.variant.stock}")
            else:
                order_item.product.stock += order_item.quantity
                order_item.product.save()
                order_item.product.refresh_from_db()
                print(f"Incremented stock for {order_item.product.name} by {order_item.quantity}. New stock: {order_item.product.stock}")
            
            # Check if all items are returned
            order.check_all_items_returned()
            
            return JsonResponse({
                "success": True,
                "message": "Return request submitted successfully.",
                "all_returned": order.status == "Returned",
                "item_id": item_id
            })
    except Order.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": "Order not found or does not belong to you."
        })
    except OrderItem.DoesNotExist:
        return JsonResponse({
            "success": False,
            "message": "Order item not found."
        })
    except Exception as e:
        print(f"Error processing return request: {str(e)}")
        return JsonResponse({
            "success": False,
            "message": f"An error occurred: {str(e)}"
        })
    
    
@login_required
@csrf_protect
@require_POST
def approve_return(request, order_id):
    print(f"Approve return endpoint hit for Order {order_id} at {timezone.now()}")
    try:
        order = Order.objects.get(id=order_id)
        print(f"Order {order_id} found - Current status: {order.status}")

        if order.status != "Return Requested":
            print(f"Order {order_id} not eligible for return - Status: {order.status}")
            return JsonResponse({"success": False, "message": "Order is not in Return Requested status"})

        print(f"Approving return for Order {order_id} - Current status: {order.status}")

        # Use a transaction to ensure atomicity
        with transaction.atomic():
            # Update order status
            order.status = "Returned"
            order.save()

            # Process return (this will handle wallet and transaction creation)
            order.process_return()

        updated_order = Order.objects.get(id=order_id)
        wallet = Wallet.objects.get(user=order.user)
        
        # Find the latest transaction for this order
        latest_transaction = Transaction.objects.filter(
            order=order, 
            transaction_type="CREDIT"
        ).order_by('-created_at').first()

        print(f"Return approved - Order {order_id} now: {updated_order.status}")

        return JsonResponse({
            "success": True, 
            "message": "Return approved and refund processed",
            "status": updated_order.status,
            "wallet_balance": float(wallet.balance),
            "transaction_id": latest_transaction.id if latest_transaction else None
        })
    except Order.DoesNotExist:
        return JsonResponse({"success": False, "message": "Order not found"})
    except Exception as e:
        print(f"Error approving return for order {order_id}: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)})
    
# This view seems redundant given approve_return handles the full order return
# If intended for a different purpose, clarify its use case
@login_required
@csrf_exempt
@require_POST
def return_product(request, product_id):
    try:
        product = get_object_or_404(Product, id=product_id)
        # Assuming this is for a specific use case outside order context
        product.quantity += 1  # Adjust this logic if tied to an order
        product.save()
        return JsonResponse({
            "success": True,
            "message": "Product stock increased successfully.",
            "new_quantity": product.quantity
        })
    except Exception as e:
        return JsonResponse({"success": False, "message": f"An error occurred: {str(e)}"}, status=500)
    
def product_stock(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    return JsonResponse({'stock': product.stock})

@csrf_exempt
@login_required
def add_to_wishlist(request, product_id):
    logger.info(f"add_to_wishlist called with product_id: {product_id}, Method: {request.method}, User: {request.user}")
    if request.method != 'POST':
        logger.error("Invalid request method")
        return JsonResponse({'success': False, 'message': 'Invalid request method'})

    try:
        # Parse the request body to get variant_id
        body = json.loads(request.body) if request.body else {}
        variant_id = body.get('variant_id')
        
        # Get the product
        product = Product.objects.get(id=product_id)
        logger.info(f"Product found: {product.name}")

        # Get the variant if provided
        variant = None
        if variant_id:
            try:
                variant = Variant.objects.get(id=variant_id, product=product)
                logger.info(f"Variant found: {variant_id}")
            except Variant.DoesNotExist:
                logger.error(f"Variant not found: {variant_id}")
                return JsonResponse({'success': False, 'message': 'Invalid product variant'})

        # Check if the item already exists in the wishlist (based on user, product, and variant)
        if variant:
            wishlist_item, created = Wishlist.objects.get_or_create(
                user=request.user,
                product=product,
                variant=variant,
                defaults={'added_at': timezone.now()}
            )
        else:
            wishlist_item, created = Wishlist.objects.get_or_create(
                user=request.user,
                product=product,
                variant=None,  # Explicitly set to None if no variant
                defaults={'added_at': timezone.now()}
            )

        logger.info(f"Wishlist item created: {created}, ID: {wishlist_item.id}")

        wishlist_count = Wishlist.objects.filter(user=request.user).count()
        logger.info(f"Wishlist count: {wishlist_count}")

        if created:
            logger.info("Item added to wishlist")
            return JsonResponse({
                'success': True,
                'message': 'Added to Wishlist!',
                'wishlist_count': wishlist_count
            })
        else:
            wishlist_item.delete()
            wishlist_count = Wishlist.objects.filter(user=request.user).count()
            logger.info("Item removed from wishlist")
            return JsonResponse({
                'success': True,
                'message': 'Removed from Wishlist!',
                'wishlist_count': wishlist_count
            })
    except Product.DoesNotExist:
        logger.error(f"Product not found: {product_id}")
        return JsonResponse({'success': False, 'message': 'Product not found'})
    except Exception as e:
        logger.error(f"Error in add_to_wishlist: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})
    
@login_required
def remove_from_wishlist(request, wishlist_id):
    if request.method == 'POST':
        try:
            wishlist_item = Wishlist.objects.get(id=wishlist_id, user=request.user)
            variant_info = f"Variant: {wishlist_item.variant.id}" if wishlist_item.variant else "No variant"
            logger.info(f"Removing wishlist item {wishlist_id} for user {request.user}. {variant_info}")
            wishlist_item.delete()
            wishlist_count = Wishlist.objects.filter(user=request.user).count()
            logger.info(f"Updated wishlist count: {wishlist_count}")
            return JsonResponse({
                'success': True,
                'message': 'Removed from Wishlist!',
                'wishlist_count': wishlist_count
            })
        except Wishlist.DoesNotExist:
            logger.error(f"Wishlist item {wishlist_id} not found for user {request.user}")
            return JsonResponse({'success': False, 'message': 'Item not found in wishlist'})
        except Exception as e:
            logger.error(f"Error in remove_from_wishlist: {str(e)}")
            return JsonResponse({'success': False, 'message': str(e)})
    logger.error("Invalid request method for remove_from_wishlist")
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
def wishlist(request):
    wishlist_items = Wishlist.objects.filter(user=request.user)
    wishlist_with_offers = []

    for item in wishlist_items:
        product = item.product
        first_variant = product.variants.first()
        original_price = first_variant.price if first_variant else Decimal('0.00')
        
        # Calculate the offer discount using Offer model's get_total_offer
        offer_discount = Decimal('0.00')
        if first_variant:
            # Call get_total_offer from Offer model
            offer = Offer.objects.filter(
                models.Q(scope='PRODUCT', product=product) |
                models.Q(scope='CATEGORY', category=product.category),
                status=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            ).first()
            if offer:
                offer_discount = offer.get_total_offer(product)
        
        discounted_price = original_price - offer_discount if offer_discount else original_price

        wishlist_with_offers.append({
            'item': item,
            'original_price': original_price,
            'discounted_price': discounted_price,
            'offer_discount': offer_discount,
            'has_offer': offer_discount > Decimal('0.00')
        })
    
    # Pagination
    paginator = Paginator(wishlist_with_offers, 3)  # Show 3 products per page
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    context = {
        'wishlist_items': page_obj,
        'page_obj': page_obj,  # Including the page object for pagination controls
    }
    return render(request, 'wishlist.html', context)

@login_required
def get_wishlist_items(request):
    items = Wishlist.objects.filter(user=request.user).values(
        'product__name',
        'product__image',  # Add this
        'product__price',  # Optional: more fields
        'product__stock'   # Optional: more fields
    )
    logger.info(f"Wishlist items for {request.user}: {list(items)}")
    return JsonResponse({'items': list(items)})

@login_required
def get_cart_count(request):
    cart_count = Cart.objects.filter(user=request.user).count()  # Adjust based on your Cart model
    return JsonResponse({'cart_count': cart_count})

@login_required
def get_wishlist_count(request):
    wishlist_count = Wishlist.objects.filter(user=request.user).count()  # Use database model
    logger.info(f"Wishlist count for {request.user}: {wishlist_count}")
    return JsonResponse({"wishlist_count": wishlist_count})

# In views.py, modify the wallet_view function
@login_required
def wallet_view(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all().select_related(
        'order'
    ).prefetch_related(
        'order__items',
        'order__items__product',
        'order__items__variant'
    ).order_by('-created_at')
    
    for transaction in transactions:
        print(f"Transaction ID: {transaction.id}")
        print(f"Type: {transaction.transaction_type}")
        print(f"Amount: {transaction.amount}")
        print(f"Order: {transaction.order_id if transaction.order else 'No Order'}")
        print(f"Description: {transaction.description}")
        
        # If it's a returned order, print more details
        if transaction.order and transaction.order.status == 'Returned':
            print("Returned Order Details:")
            for item in transaction.order.items.all():
                print(f"  - Product: {item.product.name}")
                if item.variant:
                    print(f"    Variant: {item.variant.ram}/{item.variant.storage}/{item.variant.color}")
                print(f"    Quantity: {item.quantity}")
    
    return render(request, 'wallet.html', {
        'wallet': wallet,
        'transactions': transactions,
    })

@login_required
@require_POST
def add_to_wallet(request):
    try:
        amount = Decimal(request.POST.get('amount', '0'))
        if amount <= 0:
            return JsonResponse({'success': False, 'message': 'Amount must be positive'})
        
        wallet, created = Wallet.objects.get_or_create(user=request.user)
        wallet.add_funds(amount)
        return JsonResponse({
            'success': True,
            'new_balance': str(wallet.balance),
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'message': str(e)})
    except Exception as e:
        return JsonResponse({'success': False, 'message': 'An error occurred'})

@login_required
def test_return_order(request, order_id):
    """Temporary view to test the return process"""
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        order.status = 'Returned'
        order.save()  # This should trigger the process_return method
        return JsonResponse({'success': True, 'message': 'Order marked as returned'})
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'})
    
@login_required
def process_return_request(request, order_id):
    # Your existing code to validate the return request
    
    # Update the order status
    order = Order.objects.get(id=order_id, user=request.user)
    order.status = 'Returned'
    order.save()  # This should now trigger the process_return method
    
    # Redirect or return a response
    return redirect('order_details')

@login_required
def test_return_refund(request, order_id):
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        print(f"Testing return for order #{order_id}, current status: {order.status}")
        if order.status not in ['Delivered', 'Shipped']:
            return JsonResponse({'success': False, 'message': 'This order is not eligible for return'})
        order.status = 'Returned'
        order.save()
        return JsonResponse({'success': True, 'message': 'Order returned and refund processed successfully'})
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Error: {str(e)}'})
    
def test_order_return(self):
    # Create a user
    user = CustomUser.objects.create(email='test@example.com', username='testuser')
    
    # Create a wallet for the user
    wallet = Wallet.objects.create(user=user, balance=0.00)
    
    # Create an order
    order = Order.objects.create(
        user=user,
        total_price=100.00,
        status='Delivered',
        payment_method='Wallet'
    )
    
    # Add items to the order
    product = Product.objects.create(name='Test Product', price=50.00)
    OrderItem.objects.create(order=order, product=product, quantity=2, price=50.00)
    
    # Mark the order as returned
    order.status = 'Returned'
    order.save()
    
    # Verify that the wallet balance is updated
    wallet.refresh_from_db()
    self.assertEqual(wallet.balance, Decimal('100.00'))
    
    # Verify that the transaction history contains the refund details
    transaction = Transaction.objects.filter(order=order).first()
    self.assertIsNotNone(transaction)
    self.assertIn('Refund for returned order', transaction.description)

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

# Add this to your views.py
@login_required
def force_return_order(request, order_id):
    try:
        order = Order.objects.get(id=order_id, user=request.user)
        old_status = order.status
        order.status = 'Returned'
        order.save()
        
        # Check if transaction was created
        transaction = Transaction.objects.filter(order=order).last()
        
        if transaction:
            return JsonResponse({
                'success': True, 
                'message': f'Order status changed from {old_status} to Returned. Transaction created: {transaction.id}'
            })
        else:
            return JsonResponse({
                'success': False, 
                'message': 'Order status changed but no transaction was created'
            })
    except Order.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Order not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)})