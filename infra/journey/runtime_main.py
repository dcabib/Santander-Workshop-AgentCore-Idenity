import logging

from santander_demo.journey.runtime import create_server

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    create_server().run(transport="streamable-http")
