from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.authentication.models import Key
from apps.captchas.repository import CaptchaTaskRepository


class AdministratorCreationForm(forms.Form):
    username = forms.CharField(max_length=150, label=_("Usuário"))
    email = forms.EmailField(required=False, label=_("E-mail"))
    password = forms.CharField(
        widget=forms.PasswordInput, min_length=12, label=_("Senha")
    )
    password_confirmation = forms.CharField(
        widget=forms.PasswordInput, min_length=12, label=_("Confirmação da senha")
    )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") != cleaned.get("password_confirmation"):
            raise forms.ValidationError(_("As senhas não coincidem."))
        if User.objects.filter(username=cleaned.get("username")).exists():
            raise forms.ValidationError(_("Este usuário já existe."))
        return cleaned


def sign_in(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect("management-dashboard")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = authenticate(
            request,
            username=form.cleaned_data["username"],
            password=form.cleaned_data["password"],
        )
        if user is not None:
            login(request, user)
            return redirect(request.GET.get("next") or "management-dashboard")
    return render(request, "management/login.html", {"form": form})


@login_required
def sign_out(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect("management-login")


@login_required
def dashboard(request: HttpRequest) -> HttpResponse:
    keys = (
        Key.objects.all()
        if request.user.is_staff
        else Key.objects.filter(owner=request.user)
    )
    running_tasks = []
    repository = CaptchaTaskRepository()
    for key in keys:
        for task in repository.running_for_key(key.pk):
            task["api_key_label"] = key.api_key
            if task["status"] == "pending":
                task["status"] = "processing"
            running_tasks.append(task)
    return render(
        request,
        "management/dashboard.html",
        {
            "keys": keys,
            "running_tasks": running_tasks,
            "is_admin": request.user.is_staff,
        },
    )


@login_required
def documentation(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "captchas/api_docs.html",
        {"title": _("Documentação da API de CAPTCHAs"), "key_threads": "configuradas"},
    )


@user_passes_test(lambda user: user.is_staff, login_url="management-dashboard")
def renew_key(request: HttpRequest, key_id: int) -> HttpResponse:
    key = get_object_or_404(Key, pk=key_id)
    if request.method == "POST":
        try:
            days = max(1, min(int(request.POST.get("days", "30")), 3650))
        except ValueError:
            days = 30
        start = max(key.expires_at or timezone.now(), timezone.now())
        key.expires_at = start + timedelta(days=days)
        key.save(update_fields=["expires_at"])
        messages.success(request, _("Chave renovada com sucesso."))
    return redirect("management-dashboard")


@user_passes_test(lambda user: user.is_staff, login_url="management-dashboard")
def delete_key(request: HttpRequest, key_id: int) -> HttpResponse:
    key = get_object_or_404(Key, pk=key_id)
    if request.method == "POST":
        key.delete()
        messages.success(request, _("Chave removida com sucesso."))
    return redirect("management-dashboard")


@user_passes_test(lambda user: user.is_superuser, login_url="management-dashboard")
def user_management(request: HttpRequest) -> HttpResponse:
    form = AdministratorCreationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        User.objects.create_user(
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
            is_staff=True,
        )
        messages.success(request, _("Administrador criado com sucesso."))
        return redirect("management-users")
    return render(
        request, "management/users.html", {"users": User.objects.all(), "form": form}
    )


@user_passes_test(lambda user: user.is_superuser, login_url="management-dashboard")
def deactivate_user(request: HttpRequest, user_id: int) -> HttpResponse:
    user = get_object_or_404(User, pk=user_id)
    if request.method == "POST" and user != request.user:
        user.is_active = False
        user.save(update_fields=["is_active"])
        messages.success(request, _("Usuário desativado com sucesso."))
    return redirect("management-users")
