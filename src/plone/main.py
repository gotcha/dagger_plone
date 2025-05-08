import dagger
from dagger import dag, function, object_type


DEFAULT_BUILDOUT_CONTENT = """
[buildout]
"""

@object_type
class Plone:
    @function
    def with_buildout(self, python: dagger.Container, buildout_version: str="4.1.9") -> dagger.Container:
        """Returns a container with buildout installed"""
        assert python.with_exec("python --version".split())
        return (python
          .with_exec(["apt-get", "update"])
          .with_exec("python -m venv /app".split())
          .with_exec("/app/bin/pip install zc.buildout==${buildout_version}".split())
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
