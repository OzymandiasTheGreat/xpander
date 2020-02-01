#!/usr/bin/env python3
from setuptools import setup


scripts = ['src/xpander.py']

packages = ['xpander_py', 'xpander_data', 'xpander_data.examples']

package_dir = {
	'xpander_py': 'src/xpander_py',
	'xpander_data': 'src/xpander_data',
}

package_data = {'': ['*']}

install_requires = [
	'appdirs>=1.4,<2.0',
	'klembord>=0.2.1,<0.3.0',
	'macpy>=0.1.2,<0.2.0',
	'Jinja2>=2.11.1,<3.0.0',
	'MarkupSafe>=1.1.1,<2.0.0',
]

extras_require = {
	':python_version < "3.7"': ['importlib_resources>=1.0.2,<2.0.0']
}

setup_kwargs = {
	'name': 'xpander',
	'version': '3.0.0rc0',
	'description': 'Text expander for Windows and Linux.',
	'long_description': None,
	'author': 'Ozymandias',
	'author_email': 'tomas.rav@gmail.com',
	'url': 'https://github.com/OzymandiasTheGreat/xpander',
	'scripts': scripts,
	'packages': packages,
	'package_dir': package_dir,
	'package_data': package_data,
	'install_requires': install_requires,
	'extras_require': extras_require,
	'python_requires': '>=3.7,<4.0',
}


setup(**setup_kwargs)
