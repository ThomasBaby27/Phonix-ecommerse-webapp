from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('', views.home,name='home'),
    path('shop/', views.shop_page, name='shop_page'),
   
    path('search/',views.search_products, name='search_products'),
    path('brand/<int:brand_id>/', views.brand_products, name='brand_products'),  
    path('product/<int:product_id>/', views.mobile_details, name='mobile_detail'),
    path('laptop/<int:laptop_id>/',views.laptop_detail, name='laptop_detail'),
    path('profile/',views.account_profile, name='account_profile'),
    path('update-profile/',views.update_account_profile, name='update_profile'),
    path('manage_address/',views.manage_address, name='manage_address'),
    path('add_address/',views.add_address, name='add_address'),
    path('edit_address/<int:pk>/', views.edit_address, name='edit_address'),
    path('delete_address/<int:pk>/', views.delete_address, name='delete_address'),
    path('cart/', views.cart_view, name='cart'),
    #path('cart/add/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('add_to_cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),

    path('update_cart_quantity/<int:product_id>/<str:action>/', views.update_cart_quantity, name='update_cart_quantity'),
    path('remove_from_cart/<int:product_id>/', views.remove_from_cart, name='remove_from_cart'),
    # path('get-checkout/', views.getCheckout,name='get-checkout'),
    path('checkout/',views.checkout,name='checkout'),
    path('place_order/', views.place_order, name='place_order'),
    path('add-to-wishlist/<int:product_id>/',views.add_to_wishlist, name='add_to_wishlist'),
    path('order-success/<int:order_id>/', views.order_success, name='order_success'),
    path('order_details/', views.order_details, name='order_details'),
    path('get_order_statuses/', views.get_order_statuses, name='get_order_statuses'),
    path('orders/<int:order_id>/', views.order_fulldetail_view, name='order_fulldetail_view'),
    path('cancel-order/<int:order_id>/',views.cancel_order, name='cancel_order'),
    path('place_order/<int:product_id>/', views.place_order, name='place_order'),
    path('return_product/<int:product_id>/', views.return_product, name='return_product'),
    path('return-order/<int:order_id>/', views.return_order, name='return_order'),
    path('approve-return/<int:order_id>/', views.approve_return, name='approve_return'),
    path('product-stock/<int:product_id>/', views.product_stock, name='product_stock'),
    path('invoice/<int:order_id>/', views.generate_invoice_pdf, name='generate_invoice_pdf'),
    path('wishlist/',views.wishlist, name='wishlist'),
    path('wishlist/add/<int:product_id>/',views.add_to_wishlist, name='add_to_wishlist'),
    path('wishlist/remove/<int:wishlist_id>/',views.remove_from_wishlist, name='remove_from_wishlist'),
    path('get_wishlist_items/', views.get_wishlist_items, name='get_wishlist_items'),
    path('get_cart_count/', views.get_cart_count, name='get_cart_count'),
    path('get_wishlist_count/', views.get_wishlist_count, name='get_wishlist_count'),
    path('wallet/', views.wallet_view, name='wallet'),
    path('add-to-wallet/', views.add_to_wallet, name='add_to_wallet'),
    path('get_default_variant/<int:product_id>/', views.get_default_variant, name='get_default_variant'),
    path('add_to_cart_with_variant/<int:variant_id>/', views.add_to_cart_with_variant, name='add_to_cart_with_variant'),
]+static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) 