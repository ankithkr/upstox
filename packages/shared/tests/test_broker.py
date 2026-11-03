import pytest

from shared.broker import Broker


def test_broker_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Broker()


def test_broker_subclass_must_implement_all_methods():
    class IncompleteBroker(Broker):
        async def place_order(self, order):
            return None

    with pytest.raises(TypeError):
        IncompleteBroker()
