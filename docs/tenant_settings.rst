=================================
Loading settings based on tenants
=================================

Middleware to override settings by tenants
------------------------------------------

A base middleware class is provided to load new settings based on the tenant. You need to override its ``load_tenant_settings(tenant, tenant_settings, last_time)`` method so that it load settings in the ``tenant_settings`` object and return a tuple ``new_tenant_settings, new_last_time``.

Any settings loading middleware must be loaded after the ``TenantMiddleware`` middleware as it needs ``request.tenant`` to bet set.

An example child class ``tenant_schemass.middleware.PythonSettingsMiddleware`` is provided which load settings from a Python file on the filesystem.

.. code-block:: python

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
