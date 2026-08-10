from ninja import NinjaAPI

from apps.captchas.api import captchas_router

api_v1 = NinjaAPI()

api_v1.add_router("tasks", captchas_router)
