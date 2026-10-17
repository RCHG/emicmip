# Sphinx configuration of the emicmip user documentation (GitHub Pages).
#
# Build locally (needs sphinx, myst-parser, sphinx-rtd-theme, sphinxcontrib-mermaid):
#   sphinx-build -b html doc/web doc/web/_build/html
# The cheatsheet is compiled by the GitHub Action into doc/web/_extra/ and published next
# to the pages (emicmip-cheatsheet.pdf).

project = "emicmip"
author = "Ramiro Checa-Garcia (KNMI)"
copyright = "KNMI"

extensions = ["myst_parser", "sphinxcontrib.mermaid"]
myst_enable_extensions = ["colon_fence", "deflist", "dollarmath"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown"}
exclude_patterns = ["_build", "_extra", "README.md"]

html_title = "emicmip"
html_logo = "../png/emicmip-icon.png"      # drawing only: the name is already above it
html_favicon = "../png/emicmip-favicon.png"
html_extra_path = ["_extra"]
html_static_path = ["_static"]
html_show_sourcelink = False
mermaid_height = "auto"   # default 500px leaves empty space around small diagrams

# Read the Docs theme: every page listed on the left, the current one unfolds its sections
html_theme = "sphinx_rtd_theme"
html_theme_options = {"collapse_navigation": False, "navigation_depth": 3,
                      "sticky_navigation": True}
html_css_files = ["custom.css"]
