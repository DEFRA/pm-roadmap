from django.urls import path
from . import views, api

app_name = 'roadmap'

urlpatterns = [
    path('', views.roadmap_list, name='list'),
    path('<int:pk>/', views.roadmap_detail, name='detail'),
    path('health', api.health, name='health'),

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
