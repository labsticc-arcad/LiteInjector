# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'LiteInjector'
copyright = '2023, Adam Henault'
author = 'Adam Henault'
release = ''

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinxcontrib.images',
    'sphinx.ext.autosummary',
    'sphinx_copybutton',
    'sphinx_favicon',
    'sphinx_rtd_theme'
]

favicons = [
   {
      "sizes": "16x16",
      "href": "favicon-16x16.png",
   },
   {
      "sizes": "32x32",
      "href": "favicon-32x32.png",
   },
   {
      "rel": "apple-touch-icon",
      "sizes": "180x180",
      "href": "apple-touch-icon.png",  # use a local file in _static
   },
]

templates_path = ['_templates']
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_logo = '_static/logo.png'
html_theme_options = {
    'style_nav_header_background': '#DDDDDD'
}
