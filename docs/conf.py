# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'PutPlace'
copyright = '2025, Joe Drumgoole'
author = 'Joe Drumgoole'
release = '0.4.2'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'myst_parser',  # Markdown support
    'sphinx.ext.autodoc',  # Auto-generate docs from docstrings
    'sphinx.ext.napoleon',  # Support for NumPy and Google style docstrings
    'sphinx.ext.viewcode',  # Add links to highlighted source code
    'sphinx.ext.intersphinx',  # Link to other project's documentation
]

templates_path = ['_templates']
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']

# -- Options for MyST parser -------------------------------------------------
# https://myst-parser.readthedocs.io/en/latest/configuration.html

myst_enable_extensions = [
    "colon_fence",  # ::: syntax for directives
    "deflist",  # Definition lists
    "fieldlist",  # Field lists
    "html_image",  # HTML images
    "linkify",  # Auto-convert URLs to links
    "replacements",  # Text replacements
    "smartquotes",  # Smart quotes
    "strikethrough",  # ~~strikethrough~~
    "tasklist",  # - [ ] Task lists
]

# Enable heading anchors
myst_heading_anchors = 3

# -- Options for intersphinx -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html

intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'fastapi': ('https://fastapi.tiangolo.com', None),
    'pydantic': ('https://docs.pydantic.dev/latest/', None),
    'pymongo': ('https://pymongo.readthedocs.io/en/stable/', None),
}

# -- Options for autodoc -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

# -- Theme options -----------------------------------------------------------
# https://sphinx-rtd-theme.readthedocs.io/en/stable/configuring.html

html_theme_options = {
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': False,
    'style_nav_header_background': '#2980B9',
    # Toc options
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False
}

# -- HTML context ------------------------------------------------------------

html_context = {
    "display_github": True,
    "github_user": "jdrumgoole",
    "github_repo": "putplace",
    "github_version": "main",
    "conf_py_path": "/docs/",
}

# -- Project-specific options ------------------------------------------------

# Add any paths that contain custom static files (such as style sheets)
html_static_path = []  # Empty since we don't have custom static files yet

# Logo and favicon (add when available)
# html_logo = '_static/logo.png'
# html_favicon = '_static/favicon.ico'

# Output file base name for HTML help builder
htmlhelp_basename = 'PutPlacedoc'

# -- Options for LaTeX output ------------------------------------------------

latex_elements = {
    'papersize': 'letterpaper',
    'pointsize': '10pt',
}

# Grouping the document tree into LaTeX files
latex_documents = [
    ('index', 'PutPlace.tex', 'PutPlace Documentation',
     'Joe Drumgoole', 'manual'),
]

# -- Options for manual page output ------------------------------------------

# One entry per manual page
man_pages = [
    ('index', 'putplace', 'PutPlace Documentation',
     [author], 1)
]

# -- Options for Texinfo output ----------------------------------------------

# Grouping the document tree into Texinfo files
texinfo_documents = [
    ('index', 'PutPlace', 'PutPlace Documentation',
     author, 'PutPlace', 'Distributed file metadata storage and content deduplication.',
     'Miscellaneous'),
]
