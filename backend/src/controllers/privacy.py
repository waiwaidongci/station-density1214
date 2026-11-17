from ..services import privacy
class PrivacyController:
    budget=staticmethod(privacy.budget_view)
    list=staticmethod(privacy.list_releases)
    publish=staticmethod(privacy.publish)
    public=staticmethod(privacy.list_public)
