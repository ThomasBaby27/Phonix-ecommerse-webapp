from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

class MyAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        return False  # Disable the signup form

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return True  
    def pre_social_login(self, request, sociallogin):
        user_model = get_user_model()
        user_email = sociallogin.user.email

        if not user_email:
            return  # Ignore if no email is returned

        try:
            existing_user = user_model.objects.get(email=user_email)
            sociallogin.connect(request, existing_user)  # Auto-link the account
        except user_model.DoesNotExist:
            pass  # Let Allauth handle new user creation

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        user.is_active = True  # Auto-activate user
        user.save()
        return user

