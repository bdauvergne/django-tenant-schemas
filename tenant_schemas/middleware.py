import os
from django.conf import settings, UserSettingsHolder
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.shortcuts import get_object_or_404
from tenant_schemas.utils import get_tenant_model, remove_www_and_dev, get_public_schema_name


class TenantMiddleware(object):
    """
    This middleware should be placed at the very top of the middleware stack.
    Selects the proper database schema using the request host. Can fail in
    various ways which is better than corrupting or revealing data...
    """
    def hostname_from_request(self, request):
        """ Extracts hostname from request. Used for custom requests filtering.
            By default removes the request's port and common prefixes.
        """
        return remove_www_and_dev(request.get_host().split(':')[0])

    def process_request(self, request):
        # connection needs first to be at the public schema, as this is where the
        # tenant informations are saved
        connection.set_schema_to_public()
        hostname = self.hostname_from_request(request)

        request.tenant = get_object_or_404(get_tenant_model(), domain_url=hostname)
        connection.set_tenant(request.tenant)

        # content type can no longer be cached as public and tenant schemas have different
        # models. if someone wants to change this, the cache needs to be separated between
        # public and shared schemas. if this cache isn't cleared, this can cause permission
        # problems. for example, on public, a particular model has id 14, but on the tenants
        # it has the id 15. if 14 is cached instead of 15, the permissions for the wrong
        # model will be fetched.
        ContentType.objects.clear_cache()

        # do we have a public-specific token?
        if hasattr(settings, 'PUBLIC_SCHEMA_URLCONF') and request.tenant.schema_name == get_public_schema_name():
            request.urlconf = settings.PUBLIC_SCHEMA_URLCONF

class TenantSettingBaseMiddleware(object):
    '''Base middleware classe for loading settings based on tenants

       Child classes MUST override the load_tenant_settings() method.
    '''
    def __init__(self, *args, **kwargs):
        self.wrapped = settings._wrapped
        self.tenants_settings = {}

    def get_tenant_settings(self, tenant):
        '''Get last loaded settings for tenant, try to update it by loading
           settings again is last loading time is less recent thant settings data
           store. Compare with last modification time is done in the
           load_tenant_settings() method.
        '''
        tenant_settings, last_time = self.tenants_settings.get(tenant.schema_name, (None,None))
        if tenant_settings is None:
            tenant_settings = UserSettingsHolder(self.wrapped)
        tenant_settings, last_time = self.load_settings(tenant_settings, last_time)
        self.tenants_settings[tenant.schema_name] = tenant_settings, last_time
        return tenant_settings

    def load_tenant_settings(self, tenant_settings, last_time):
        '''Load tenant settings into tenant_settings object, eventually skip if
           last_time is more recent than last update time for settings and return
           the new value for tenant_settings and last_time'''
        raise NotImplemented

    def process_request(self, request):
        settings._wrapped = self.get_tenant_settings(request.tenant)

    def process_response(self, request, response):
        settings._wrapped = self.wrapped
        return response

class PythonSettingsMiddleware(object):
    '''Load settings from a file whose path is given by:

            os.path.join(settings.TENANT_PYTHON_SETTINGS % schema_name, 'settings.py')

       The file is executed in the same context as the classic settings file
       using execfile.
    '''
    def load_tenant_settings(self, tenant, tenant_settings, last_time):
        path = os.path.join(settings.TENANT_PYTHON_SETTINGS % tenant.schema_name, 'settings.py')
        st_mtime = os.stat(path).st_mtime
        if not last_time or st_mtime >= last_time:
            tenant_settings = UserSettingsHolder(self.wrapped)
            execfile(path, tenant_settings)
            return tenant_settings, st_mtime
        else:
            return tenant_settings, last_time
