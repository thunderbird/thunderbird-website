class Provider:
    """ Generic data provider. Extend and implement the query function to use. """

    def __init__(self, name: str, auth_options: dict):
        self.name = name
        self.auth_options = auth_options

    def query(self, country: str, year: int, additional_options: dict):
        """ Query the data provider and return the results. Additional options includes non-standard parameters that may be critical for a particular provider. """
        raise NotImplementedError()

    def build(self, country: str, year: int, additional_options: dict):
        """ Calls query with the provided data, builds, and returns a list of models with the standardized data. """
        raise NotImplementedError()
