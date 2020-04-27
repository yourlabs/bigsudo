from setuptools import setup

setup(
    name='bigsudo',
    versioning='dev',
    url='https://yourlabs.io/oss/bigsudo',
    setup_requires='setupmeta',
    keywords='automation cli ansible',
    python_requires='>=3',
    include_package_data=True,
    entry_points={
        'console_scripts': [
            'bigsudo = bigsudo.console_script:cli.entry_point',
        ],
    },
)
