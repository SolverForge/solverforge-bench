from pydantic import BaseModel, ConfigDict
import numpy as np


class Instance(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    comment: str
    dimension: int
    edge_weight_type: str
    capacity: int
    node_coord: np.ndarray  # n x 2 matrix
    demand: np.ndarray  #  n vector
    depot: np.ndarray  # only 1 entry
    edge_weight: np.ndarray  # n x n matrix


class Solution(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    routes: list
    cost: int
