import abc


class DebeziumInterface(object, metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def is_generator(self) -> bool:
        pass

    @abc.abstractmethod
    def generate_config(self) -> dict:
        pass
