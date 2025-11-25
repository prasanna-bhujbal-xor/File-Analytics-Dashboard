from django.urls import path
from . import views

urlpatterns=[
    path('',views.home_view,name='home'),
    path('about',views.about_view,name='about'),
    path('signup/', views.signup_view, name='signup'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('api/user/me/', views.CurrentUserAPIView.as_view(), name='api-current-user'),
    path('api/files/', views.FileListCreateAPIView.as_view(), name='api-file-list'),
    path('api/files/<int:pk>/', views.FileDetailAPIView.as_view(), name='api-file-detail'),
    path('api/analytics/', views.DashboardAnalyticsAPIView.as_view(), name='api-analytics'),
    path('api/scan_shared/', views.RescanSharedFolderAPIView.as_view(), name='api-rescan-shared'),
    path('api/files/<int:pk>/access/', views.FileAccessAPIView.as_view(), name='api-file-access'),
    path('shared_files/<path:rel_path>/', views.serve_shared_file, name='serve-shared-file'),
    path('api/files/<int:pk>/content/', views.FileContentAPIView.as_view(), name='api-file-content'),



]
    


