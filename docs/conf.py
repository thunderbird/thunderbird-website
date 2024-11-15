# Configuration file for the Sphinx documentation builder.

# -- Project information

project = 'Thunderbird Websites'
copyright = '2024, MZLA Technologies Corporation'
author = 'MZLA Technologies Corporation'

release = '0.1'
version = '0.1.0'

# -- General configuration

extensions = [
    'sphinx.ext.duration',
    'sphinx.ext.doctest',
    'sphinx.ext.autodoc',
    'sphinx.ext.autosummary',
    'sphinx.ext.intersphinx',
    'myst_parser',
]
# removing sphinx_rtd_light_dark extension because:
# sphinx.errors.ThemeError: An error happened in rendering the page archived.
# Reason: UndefinedError("'style' is undefined")

intersphinx_mapping = {
    'python': ('https://docs.python.org/3/', None),
    'sphinx': ('https://www.sphinx-doc.org/en/master/', None),
}
intersphinx_disabled_domains = ['std']

templates_path = ['_templates']

# -- Options for HTML output

#html_theme = 'sphinx_rtd_light_dark'
html_theme = 'sphinx_rtd_theme'

# -- Options for EPUB output
epub_show_urls = 'footnote'
