from ninja import NinjaAPI

from apps.captchas.api import captchas_router
from apps.captchas.api.docs import docs_router

api_v1 = NinjaAPI(docs_url=None)

api_v1.add_router("tasks", captchas_router)
api_v1.add_router("captchas", docs_router)
