from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from households.services import get_household_for_user

from .forms import ShoppingItemForm, ShoppingListForm
from .models import ShoppingList
from .services import (
    InvalidShoppingOperation,
    active_lists_for_user,
    add_item,
    complete_list,
    completed_lists_for_user,
    delete_item,
    grocery_summary_for_user,
    items_for_user,
    lists_for_user,
    toggle_item,
    update_item,
)


def _is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def _interaction_context(shopping_list, item_form=None):
    refreshed_list = ShoppingList.objects.with_item_counts().get(pk=shopping_list.pk)
    remaining_items = (
        refreshed_list.items.filter(is_purchased=False)
        .select_related("added_by", "purchased_by")
        .order_by("created_at")
    )
    purchased_items = (
        refreshed_list.items.filter(is_purchased=True)
        .select_related("added_by", "purchased_by")
        .order_by("-purchased_at")
    )
    return {
        "shopping_list": refreshed_list,
        "remaining_items": remaining_items,
        "purchased_items": purchased_items,
        "item_form": item_form or ShoppingItemForm(),
    }


def _require_household(request):
    household = get_household_for_user(request.user)
    if household is None:
        messages.warning(
            request,
            "Your account is not connected to a household yet. Ask an administrator to add a household membership.",
        )
    return household


@login_required
def dashboard(request):
    household = get_household_for_user(request.user)
    summary = (
        grocery_summary_for_user(request.user)
        if household
        else {"active_list_count": 0, "remaining_item_count": 0}
    )
    return render(
        request,
        "home.html",
        {"household": household, "grocery_summary": summary},
    )


@login_required
def active_lists(request):
    household = get_household_for_user(request.user)
    return render(
        request,
        "shopping/active_lists.html",
        {
            "shopping_lists": active_lists_for_user(request.user) if household else [],
            "household": household,
        },
    )


@login_required
def list_create(request):
    household = _require_household(request)
    if household is None:
        return redirect("shopping:active_lists")
    form = ShoppingListForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        shopping_list = form.save(commit=False)
        shopping_list.household = household
        shopping_list.created_by = request.user
        shopping_list.save()
        messages.success(request, "Grocery list created.")
        return redirect("shopping:list_detail", list_id=shopping_list.pk)
    return render(
        request,
        "shopping/list_form.html",
        {"form": form, "page_title": "New Grocery List", "submit_label": "Create List"},
    )


@login_required
def list_detail(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.ACTIVE),
        pk=list_id,
    )
    context = _interaction_context(shopping_list)
    return render(request, "shopping/list_detail.html", context)


@login_required
def list_edit(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.ACTIVE),
        pk=list_id,
    )
    form = ShoppingListForm(request.POST or None, instance=shopping_list)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Grocery list updated.")
        return redirect("shopping:list_detail", list_id=shopping_list.pk)
    return render(
        request,
        "shopping/list_form.html",
        {
            "form": form,
            "page_title": "Edit Grocery List",
            "submit_label": "Save Changes",
            "shopping_list": shopping_list,
        },
    )


@login_required
def list_delete(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.ACTIVE),
        pk=list_id,
    )
    if request.method == "POST":
        shopping_list.delete()
        messages.success(request, "Grocery list deleted.")
        return redirect("shopping:active_lists")
    return render(
        request, "shopping/list_confirm_delete.html", {"shopping_list": shopping_list}
    )


@login_required
def list_complete(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.ACTIVE),
        pk=list_id,
    )
    shopping_list = ShoppingList.objects.with_item_counts().get(pk=shopping_list.pk)
    if request.method == "POST":
        try:
            completed = complete_list(shopping_list=shopping_list, user=request.user)
        except InvalidShoppingOperation as error:
            messages.error(request, str(error))
            return redirect("shopping:active_lists")
        messages.success(request, "Shopping completed. The list is now in history.")
        return redirect("shopping:history_detail", list_id=completed.pk)
    return render(
        request,
        "shopping/list_complete_confirmation.html",
        {"shopping_list": shopping_list},
    )


@login_required
@require_POST
def item_add(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.ACTIVE),
        pk=list_id,
    )
    form = ShoppingItemForm(request.POST)
    if form.is_valid():
        try:
            add_item(
                shopping_list=shopping_list,
                text=form.cleaned_data["text"],
                quantity=form.cleaned_data["quantity"],
                description=form.cleaned_data["description"],
                user=request.user,
            )
        except InvalidShoppingOperation as error:
            messages.error(request, str(error))
            return redirect("shopping:active_lists")
        if _is_htmx(request):
            return render(
                request,
                "shopping/partials/list_interactions.html",
                _interaction_context(shopping_list),
            )
        return redirect("shopping:list_detail", list_id=shopping_list.pk)
    if _is_htmx(request):
        return render(
            request,
            "shopping/partials/list_interactions.html",
            _interaction_context(shopping_list, item_form=form),
            status=422,
        )
    return render(
        request,
        "shopping/list_detail.html",
        _interaction_context(shopping_list, item_form=form),
        status=422,
    )


@login_required
@require_POST
def item_toggle(request, item_id):
    item = get_object_or_404(items_for_user(request.user), pk=item_id)
    shopping_list = item.shopping_list
    try:
        toggle_item(item=item, user=request.user)
    except InvalidShoppingOperation as error:
        messages.error(request, str(error))
        return redirect("shopping:history_detail", list_id=shopping_list.pk)
    if _is_htmx(request):
        return render(
            request,
            "shopping/partials/list_interactions.html",
            _interaction_context(shopping_list),
        )
    return redirect("shopping:list_detail", list_id=shopping_list.pk)


@login_required
def item_edit(request, item_id):
    item = get_object_or_404(
        items_for_user(request.user).filter(
            shopping_list__status=ShoppingList.Status.ACTIVE
        ),
        pk=item_id,
    )
    form = ShoppingItemForm(request.POST or None, instance=item)
    if request.method == "POST" and form.is_valid():
        try:
            update_item(
                item=item,
                text=form.cleaned_data["text"],
                quantity=form.cleaned_data["quantity"],
                description=form.cleaned_data["description"],
            )
        except InvalidShoppingOperation as error:
            messages.error(request, str(error))
            return redirect("shopping:history_detail", list_id=item.shopping_list_id)
        messages.success(request, "Grocery item updated.")
        return redirect("shopping:list_detail", list_id=item.shopping_list_id)
    return render(
        request,
        "shopping/item_form.html",
        {"form": form, "item": item, "shopping_list": item.shopping_list},
    )


@login_required
@require_POST
def item_delete(request, item_id):
    item = get_object_or_404(items_for_user(request.user), pk=item_id)
    shopping_list = item.shopping_list
    try:
        delete_item(item=item)
    except InvalidShoppingOperation as error:
        messages.error(request, str(error))
        return redirect("shopping:history_detail", list_id=shopping_list.pk)
    if _is_htmx(request):
        return render(
            request,
            "shopping/partials/list_interactions.html",
            _interaction_context(shopping_list),
        )
    return redirect("shopping:list_detail", list_id=shopping_list.pk)


@login_required
def history(request):
    household = get_household_for_user(request.user)
    return render(
        request,
        "shopping/history.html",
        {
            "shopping_lists": completed_lists_for_user(request.user)
            if household
            else [],
            "household": household,
        },
    )


@login_required
def history_detail(request, list_id):
    shopping_list = get_object_or_404(
        lists_for_user(request.user).filter(status=ShoppingList.Status.COMPLETED),
        pk=list_id,
    )
    items = shopping_list.items.select_related("added_by", "purchased_by").order_by(
        "created_at"
    )
    return render(
        request,
        "shopping/history_detail.html",
        {"shopping_list": shopping_list, "items": items},
    )


@require_GET
def service_worker(request):
    response = render(
        request,
        "service-worker.js",
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response


def error_403(request, exception=None):
    return render(request, "errors/403.html", status=403)


def error_404(request, exception=None):
    return render(request, "errors/404.html", status=404)


def error_500(request):
    return render(request, "errors/500.html", status=500)
