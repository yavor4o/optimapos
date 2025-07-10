from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.Model):
    name = models.CharField(_('Name'), max_length=100, unique=True)
    code = models.SlugField(_('Code'), max_length=50, unique=True)
    description = models.TextField(_('Description'), blank=True)

    class Meta:
        verbose_name = _('Role')
        verbose_name_plural = _('Roles')

    def __str__(self):
        return self.name


class User(AbstractUser):
    role = models.ForeignKey(Role, verbose_name=_('Role'), on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(_('Phone'), max_length=20, blank=True)

    class Meta:
        verbose_name = _('User')
        verbose_name_plural = _('Users')

    def __str__(self):
        return f'{self.get_full_name() or self.username} ({self.role.name if self.role else _("No role")})'
