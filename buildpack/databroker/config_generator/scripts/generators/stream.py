import json
from buildpack.databroker.config_generator.scripts.utils import (
    template_engine_instance,
)


def generate_config(config):
    topologies = {"topologies": []}
    env = template_engine_instance()
    template = env.get_template("streaming_producer.json.j2")
    for service in config.DataBrokerConfiguration.publishedServices:
        for entity in service.entities:
            renderedTemplate = template.render(entity=entity)
            renderedTemplateAsJson = json.loads(renderedTemplate)
            topologies["topologies"].append(renderedTemplateAsJson)

    return json.dumps(topologies)
