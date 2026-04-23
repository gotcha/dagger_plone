import dagger
from dagger import dag, function, object_type


DEFAULT_BASE_IMAGE = "python:3.12"
DEFAULT_BUILDOUT_CONTENT = """
[buildout]
"""

@object_type
class Plone:
    @function
    def with_buildout(self, python: dagger.Container, buildout_version: str="5.1.3", setuptools_version: str="81.0.0") -> dagger.Container:
        """Returns a container with buildout installed"""
        assert python.with_exec("python --version".split())
        return (python
          .with_exec("python -m venv /app".split())
          .with_exec(f"/app/bin/pip install zc.buildout=={buildout_version} setuptools=={setuptools_version}".split())
        )

    @function
    def with_plone(self, buildout: dagger.Container, plone_version: str="6.0.15", devpi_volume: str="devpi_data") -> dagger.Container:
        """Install Plone into a container where buildout is installed."""
        buildout.directory('/app')
        buildout.directory('/app/bin')
        buildout.file('/app/bin/python')
        buildout.file('/app/bin/buildout')
        buildout_cfg = dag.file('buildout.cfg', DEFAULT_BUILDOUT_CONTENT)
        return (buildout
          .with_workdir("/app")
          .with_file("/app/buildout.cfg", buildout_cfg)
          .with_service_binding('devpi', self.devpi_as_service(volume_name=devpi_volume))
          .with_exec(f"/app/bin/buildout buildout:index=http://devpi:3141/root/pypi/+simple instance:recipe=plone.recipe.zope2instance versions:zc.buildout= versions.setuptools= instance:eggs=Plone buildout:parts= buildout:extends=https://dist.plone.org/release/{plone_version}/versions.cfg instance:user=admin:admin install instance".split())
          .with_exposed_port(8080)
        )

    @function
    def with_zope(self, buildout: dagger.Container, plone_version: str="6.0.15", devpi_volume: str="devpi_data") -> dagger.Container:
        """Install Zope into a container where buildout is installed."""
        buildout.directory('/app')
        buildout.directory('/app/bin')
        buildout.file('/app/bin/python')
        buildout.file('/app/bin/buildout')
        buildout_cfg = dag.file('buildout.cfg', DEFAULT_BUILDOUT_CONTENT)
        return (buildout
          .with_workdir("/app")
          .with_file("/app/buildout.cfg", buildout_cfg)
          .with_service_binding('devpi', self.devpi_as_service(volume_name=devpi_volume))
          .with_exec(f"/app/bin/buildout buildout:index=http://devpi:3141/root/pypi/+simple versions:zc.buildout= versions.setuptools= instance:recipe=plone.recipe.zope2instance instance:eggs= buildout:parts= buildout:extends=https://dist.plone.org/release/{plone_version}/versions.cfg instance:user=admin:admin install instance".split())
          .with_exposed_port(8080)
        )

    @function
    def as_service(self, base_image: str=DEFAULT_BASE_IMAGE, plone_version: str="6.1.4", devpi_volume: str="devpi_data") -> dagger.Service:
        """Run Plone as a service"""
        python = dag.container().from_(base_image)
        buildout = self.with_buildout(python)
        zope = self.with_zope(buildout, plone_version=plone_version, devpi_volume=devpi_volume)
        plone = self.with_plone(zope, plone_version=plone_version, devpi_volume=devpi_volume)
        # image_name = f"localhost/plone:{plone_version}-gc-dagger"
        return plone.as_service(args="bin/instance fg".split())

    @function
    def default_base_image(self) -> str:
        """Returns the default base image used to build Plone"""
        return DEFAULT_BASE_IMAGE

    @function
    def devpi_as_service(self, base_image: str="jonasal/devpi-server", volume_name: str="devpi_data") -> dagger.Service:
        """Run Plone as a service"""
        cache_volume = dag.cache_volume(volume_name)
        server = dag.container().from_(base_image).with_env_variable("DEVPI_PASSWORD", "password").with_exposed_port(3141).with_mounted_cache("/devpi/server", cache_volume)
        return server.as_service(args="--indexer-backend null --serverdir /devpi/server --request-timeout 60".split(), use_entrypoint=True)

    @function
    async def run_cypress(self, source: dagger.Directory, plone_service: dagger.Service) -> str:
        """Run cypress tests against Plone"""
        cypress = (dag.container().from_('cypress/included')
          .with_directory('/app', source)
          .with_workdir('/app')
          .with_service_binding('plone', plone_service)
          .with_exec("npm install cypress-terminal-report".split())
          .with_exec("cypress run --env PLONE_HOST=plone:8080 -s cypress/e2e/plone*".split())
        )
        return await cypress.stdout()

    @function
    def cypress_directory(self) -> dagger.Directory:
        """Returns module as a directory source for cypress tests"""
        return dag.git("https://github.com/gotcha/dagger_plone").head().tree()

    @function(cache="never")
    def export_cache_to_host(self, cache_volume_name: str, container_path: str = "/cache/data") -> dagger.Directory:
        """
        Export contents of a Dagger cache volume to a host directory.
        """
        cache = dag.cache_volume(cache_volume_name)

        
        directory = ( dag.container()
            .from_("alpine:latest")
            .with_mounted_cache(container_path, cache)
            .with_exec(["cp", "-r", container_path, "/tmp/cache-export"])
            .directory("/tmp/cache-export") )
        return directory

    @function
    async def import_host_to_cache(self, host_dir: dagger.Directory, cache_volume_name: str, container_path: str = "/cache/data",) -> None:
        """
        Import contents from a host directory into a Dagger cache volume.
        Existing cache content is overwritten.
        """
        cache = dag.cache_volume(cache_volume_name)

        await (
            dag.container()
            .from_("alpine:latest")
            .with_mounted_directory("/tmp/host-data", host_dir)
            .with_mounted_cache(container_path, cache)
            .with_exec(["sh", "-c", f"cp -r /tmp/host-data/. {container_path}/"])
            .sync()
        )

