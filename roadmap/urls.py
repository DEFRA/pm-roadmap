from django.urls import path
from django.views.generic import RedirectView

from . import views, api, views_okr, views_team

app_name = 'roadmap'

urlpatterns = [
    # Landing page redirects to Teams for now (temporary 302 — easy to change).
    path('', RedirectView.as_view(pattern_name='roadmap:team_list', permanent=False), name='home'),
    path('roadmaps/', views.roadmap_list, name='list'),
    path('health', api.health, name='health'),

    # ── Standalone OKR pages ──
    path('objectives/', views_okr.objective_list, name='objective_list'),
    path('objectives/new/', views_okr.objective_create, name='objective_create'),
    path('objectives/<int:pk>/edit/', views_okr.objective_edit, name='objective_edit'),
    path('objectives/<int:pk>/delete/', views_okr.objective_delete, name='objective_delete'),
    path('objectives/sets/new/', views_okr.objective_set_create, name='objective_set_create'),
    path('objectives/sets/<int:pk>/', views_okr.objective_set_detail, name='objective_set_detail'),
    path('objectives/sets/<int:pk>/edit/', views_okr.objective_set_edit, name='objective_set_edit'),
    path('objectives/sets/<int:pk>/delete/', views_okr.objective_set_delete, name='objective_set_delete'),
    path('objectives/sets/<int:pk>/archive/', views_okr.objective_set_archive, name='objective_set_archive'),
    path('objectives/sets/<int:pk>/unarchive/', views_okr.objective_set_unarchive, name='objective_set_unarchive'),

    # ── Team pages ──
    path('teams/', views_team.team_list, name='team_list'),
    path('teams/new/', views_team.team_create, name='team_create'),
    path('teams/<int:pk>/', views_team.team_home, name='team_home'),
    path('teams/<int:pk>/edit/', views_team.team_edit, name='team_edit'),

    path('<int:pk>/', views.roadmap_detail, name='detail'),

    # ── JSON API (backs the in-page modals) ──
    path('api/organisations/', api.organisations, name='api_organisations'),
    path('api/tags/', api.tags_collection, name='api_tags'),
    path('api/tags/reorder/', api.tags_reorder, name='api_tags_reorder'),
    path('api/tags/<int:pk>/', api.tag_detail, name='api_tag'),
    path('api/roadmaps/', api.roadmaps_collection, name='api_roadmaps'),
    path('api/roadmaps/<int:pk>/', api.roadmap_detail, name='api_roadmap'),
    path('api/roadmaps/<int:roadmap_pk>/items/', api.items_collection, name='api_items'),
    path('api/items/<int:pk>/', api.item_detail, name='api_item'),
]
