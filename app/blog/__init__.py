"""/blog: the English blog, its publishing API for an external writer, and the admin page that publishes it.

    app/main.py:  from app.blog import api_router, admin_router, pages_router

| module | what it owns |
|---|---|
| `config.py` | every setting, as an env var with a default - and the API token, which it never hands out |
| `paths.py` | **the one place a blog URL is spelled.** Reads the URL registry when it has the entries |
| `store.py` | the `blog_posts` and `blog_images` tables, and the draft -> published lifecycle |
| `markdown.py` | the restricted Markdown subset we accept, rendered to HTML we built ourselves |
| `safety.py` | the blocking checks a post body must pass before it can be published |
| `images.py` | uploaded images: what is accepted, where it is stored, how it is served |
| `pages.py` | the public list page and the post pages |
| `api.py` | `POST/PUT /api/blog/posts`, `POST /api/blog/images` - token auth, and posts arrive as DRAFTS |
| `admin.py` | `/admin/blog`: preview a draft, publish it in one click |

ENGLISH ONLY, AND DELIBERATELY SO - the same decision as the Hindi-only dosha guides in
app/web/dosha_guides.py, taken in the other direction. The writer writes English; a Hindi and Marathi
tree filled by machine translation would be three times the indexable surface with nothing new in it,
which is how a site collects the kind of page Search Console files under "Discovered - currently not
indexed". `paths.LANGS` is the one place that says so, the URL registry decides which trees exist, and
the day there is Hindi demand and a Hindi writer the registry entry gains "hi" and this module follows.

NOTHING HERE PUBLISHES ITSELF. A post arriving over the API is a draft, whatever the caller asked for,
unless `BLOG_AUTOPUBLISH` is on - and it is off by default and ships off. The one-click publish on
/admin/blog re-runs every check before it writes, so it is a decision rather than a bypass.
"""

from .admin import router as admin_router
from .api import router as api_router
from .pages import router as pages_router

__all__ = ["admin_router", "api_router", "pages_router"]
