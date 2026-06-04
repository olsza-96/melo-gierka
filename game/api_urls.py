from django.urls import path

from game import views

app_name = "game"

urlpatterns = [
    path("sessions/<str:code>/state", views.session_state, name="session-state"),
]