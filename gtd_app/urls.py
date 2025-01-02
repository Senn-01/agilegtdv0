from django.urls import path
from . import views

app_name = 'gtd_app'

urlpatterns = [
    # Page 1: Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    
    # Page 2: Home - Quick Capture
    path('', views.home_view, name='home'),
    
    # Page 3: Process Inbox
    path('inbox/', views.inbox_view, name='inbox'),
    
    # Page 4: Backlog
    path('backlog/', views.backlog_view, name='backlog'),
    
    # Page 5: Sprint/Kanban
    path('sprint/', views.sprint_view, name='sprint'),
    
    # Page 6: Retrospective
    path('retrospective/', views.retrospective_view, name='retrospective'),
    
    # Page 7: Archives
    path('archives/', views.archives_view, name='archives'),
    
    # Page 8: Item Details
    path('item/<str:item_type>/<int:item_id>/', views.get_item_details, name='item_details'),
] 