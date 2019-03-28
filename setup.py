from setuptools import setup

setup(
    name='nimbus-k8s-provisioner',
    description='Listens to GitHub organization events and creates peristent volumes.',
    packages=['provisioner'],
    author='Jason Boutte',
    author_email='boutte3@llnl.gov',
    version='0.1.0',
    url='https://github.com/esgf-nimbus/nimbus-k8s-provisioner',
    entry_points={
        'console_scripts': [
            'nimbus-provisioner=provisioner:main',
        ]
    },
)
