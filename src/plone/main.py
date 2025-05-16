import dagger
from dagger import dag, function, object_type


DEFAULT_BASE_IMAGE = "python:3.12"
DEFAULT_BUILDOUT_CONTENT = """
[buildout]
"""

@object_type
class Plone:
    @function
    def with_buildout(self, python: dagger.Container, buildout_version: str="4.1.9", setuptools_version: str="80.2.0") -> dagger.Container:
        """Returns a container with buildout installed"""
        assert python.with_exec("python --version".split())
        return (python
          .with_exec("python -m venv /app".split())
          .with_exec(f"/app/bin/pip install zc.buildout=={buildout_version} setuptools=={setuptools_version}".split())
        )

    @function
    def with_plone(self, buildout: dagger.Container, plone_version: str="6.0.15") -> dagger.Container:
        """Install Plone into a container where buildout is installed."""
        buildout.directory('/app')
        buildout.directory('/app/bin')
        buildout.file('/app/bin/python')
        buildout.file('/app/bin/buildout')
        buildout_cfg = dag.file('buildout.cfg', DEFAULT_BUILDOUT_CONTENT)
        return (buildout
          .with_workdir("/app")
          .with_file("/app/buildout.cfg", buildout_cfg)
          .with_exec(f"/app/bin/buildout instance:recipe=plone.recipe.zope2instance instance:eggs=Plone buildout:parts= buildout:extends=https://dist.plone.org/release/{plone_version}/versions.cfg instance:user=admin:admin install instance".split())
          .with_exposed_port(8080)
        )

    @function
    def as_service(self, base_image: str=DEFAULT_BASE_IMAGE, plone_version: str="6.1.1") -> dagger.Service:
        """Run Plone as a service"""
        python = dag.container().from_(base_image)
        buildout = self.with_buildout(python)
        plone = self.with_plone(buildout, plone_version=plone_version)
        return plone.as_service(args="bin/instance fg".split())

    @function
    def default_base_image(self) -> str:
        """Returns the default base image used to build Plone"""
        return DEFAULT_BASE_IMAGE

    @function
    def run_cypress(self, source: dagger.Directory) -> str:
        """Run cypress tests against Plone"""
        cypress = (dag.container().from_('cypress/included')
          .with_directory('/app', source)
          .with_workdir('/app')
          .with_service_binding('plone', self.as_service())
          .with_exec("cypress run --env PLONE_HOST=plone:8080 -s cypress/e2e/plone*".split())
        )
        return cypress.stdout()

    @function
    def cypress_directory(self) -> dagger.Directory:
        """Returns module as a directory source for cypress tests"""
        return dag.git("https://github.com/gotcha/dagger_plone").head().tree()
