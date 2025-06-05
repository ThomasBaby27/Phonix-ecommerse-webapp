from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin_login/', views.admin_login, name='admin_login'),
    path("admin_panel/", views.admin_panel, name="admin_panel"),
    path("dashboard/",views.dashboard_view, name="dashboard"),
    path("users/", views.users_view, name="users"),
    path("block_user/<int:user_id>/", views.block_user, name="block_user"),
    path("unblock_user/<int:user_id>/", views.unblock_user, name="unblock_user"),
    path("categories_list/", views.category_list, name="category_list"),
    path('add_category', views.add_category, name='add_category'), 
    path("categories/edit/<int:category_id>/",views.edit_category, name="edit_category"),
    path('delete_category/<int:category_id>/', views.delete_category, name='delete_category'),  # Add this line
    path('brands/', views.brand_list, name='brand_list'),
    path('brands/add/', views.add_brand, name='add_brand'),
    path('brands/edit/<int:brand_id>/', views.edit_brand, name='edit_brand'),
    path('products_list/',views.product_list, name='product_list'),
    path('add_product/',views.add_product, name='add_product'),
    path('products/<int:product_id>/add_variant/', views.add_variant, name='add_variant'),
    path('products/edit/<int:product_id>/',views.edit_product, name='edit_product'),
    path('products/delete/<int:product_id>/', views.delete_product, name='delete_product'),  
    path("toggle-product-status/<int:product_id>/",views.toggle_product_status, name="toggle_product_status"),
    path('orders_list/',views.order_list, name='order_list'),
    path("update-order-status/",views.update_order_status, name="update_order_status"),
    path('orders/<int:order_id>/', views.order_detail, name='order_detail'),
    path('get-product-quantities/', views.get_product_quantities, name='get_product_quantities'),
    path('orders/approve_return/<int:order_id>/', views.approve_return, name='approve_return'),
    path('offers/', views.offer_management, name='offer_management'),
    #path('edit-offer/<int:offer_id>/', views.edit_offer, name='edit_offer'),
    path('offers/add/', views.add_offer, name='add_offer'),
    path('offers/edit/<int:offer_id>/', views.edit_offer, name='edit_offer'),
    path('offer/delete/<int:offer_id>/', views.delete_offer, name='delete_offer'),
    path('coupon_list/', views.coupon_list, name='coupon_list'),
    path('coupons/add/', views.add_coupon, name='add_coupon'),
    path('coupons/edit/<int:coupon_id>/', views.edit_coupon, name='edit_coupon'),
    path('coupons/delete/<int:coupon_id>/', views.delete_coupon, name='delete_coupon'),
    #path('add_offer', views.add_offer, name='add_offer'),
    path('sales_report/', views.sales_report, name='sales_report'),
    path('wallets/', views.wallet_management, name='wallet_management'),
    path('transactions/<int:transaction_id>/', views.transaction_detail, name='transaction_detail'),
    path('orders/items/<int:order_id>/', views.get_order_items, name='get_order_items'),
    path("admin_logout/", views.admin_logout, name="admin_logout"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

