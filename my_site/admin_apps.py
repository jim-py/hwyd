from django.contrib.admin.apps import AdminConfig


class ProductivumAdminConfig(AdminConfig):
    default_site = 'my_site.admin_site.ProductivumAdminSite'
