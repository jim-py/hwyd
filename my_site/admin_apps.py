from django.contrib.admin.apps import AdminConfig


class ProductivumAdminConfig(AdminConfig):
    default_site = 'my_site.admin_site.ProductivumAdminSite'

    def ready(self):
        super().ready()
        from .admin_integrations import register_schedule_admins
        register_schedule_admins()
