from abc import ABC
from types import MethodType
from typing import Union, Any, List, Callable, Iterable, Dict
from collections import namedtuple


class BaseEnvManager(ABC):

    def __init__(self, env_fn: Callable, env_cfg: Iterable, env_num: int, episode_num: int, **kwargs) -> None:
        self._env_num = env_num
        self._env_fn = env_fn
        self._env_cfg = env_cfg
        if episode_num == 'inf':
            episode_num = float('inf')
        self._episode_num = episode_num
        self._closed = True

    def _create_state(self) -> None:
        # env_ref is used to acquire some common attributes of env, like obs_shape and act_shape
        self._closed = False
        self._env_ref = self._env_fn(self._env_cfg[0])
        self._env_episode_count = {i: 0 for i in range(self.env_num)}
        self._env_done = {i: False for i in range(self.env_num)}
        self._next_obs = {i: None for i in range(self.env_num)}
        self._envs = [self._env_fn(c) for c in self._env_cfg]
        assert len(self._envs) == self._env_num

    def _check_closed(self):
        assert not self._closed, "env manager is closed, please use the alive env manager"

    @property
    def env_num(self) -> int:
        return self._env_num

    @property
    def next_obs(self) -> Dict[int, Any]:
        return {i: self._next_obs[i] for i, d in self._env_done.items() if not d}

    @property
    def done(self) -> bool:
        return all(self._env_done.values())

    @property
    def method_name_list(self) -> list:
        return ['reset', 'step', 'seed', 'close']

    def __getattr__(self, key: str) -> Any:
        """
        Note: if a python object doesn't have the attribute named key, it will call this method
        """
        # we suppose that all the envs has the same attributes, if you need different envs, please
        # create different env managers.
        if not hasattr(self._env_ref, key):
            raise AttributeError("env `{}` doesn't have the attribute `{}`".format(type(self._env_ref), key))
        if isinstance(getattr(self._env_ref, key), MethodType) and key not in self.method_name_list:
            raise RuntimeError("env getattr doesn't supports method({}), please override method_name_list".format(key))
        self._check_closed()
        return [getattr(env, key) if hasattr(env, key) else None for env in self._envs]

    def launch(self, reset_param: Union[None, List[dict]] = None) -> None:
        assert self._closed, "please first close the env manager"
        self._create_state()
        self.reset(reset_param)

    def reset(self, reset_param: Union[None, List[dict]] = None) -> None:
        if reset_param is None:
            reset_param = [{} for _ in range(self.env_num)]
        self._reset_param = reset_param
        # set seed
        if hasattr(self, '_env_seed'):
            for env, s in zip(self._envs, self._env_seed):
                env.seed(s)
        for i in range(self.env_num):
            self._reset(i)

    def _reset(self, env_id: int) -> None:
        obs = self._safe_run(lambda: self._envs[env_id].reset(**self._reset_param[env_id]))
        self._next_obs[env_id] = obs

    def _safe_run(self, fn: Callable):
        try:
            return fn()
        except Exception as e:
            self.close()
            raise e

    def step(self, action: Dict[int, Any]) -> Dict[int, namedtuple]:
        self._check_closed()
        timestep = {}
        for env_id, act in action.items():
            timestep[env_id] = self._safe_run(lambda: self._envs[env_id].step(act))
            if timestep[env_id].done:
                self._env_episode_count[env_id] += 1
                if self._env_episode_count[env_id] == self._episode_num:
                    self._env_done[env_id] = True
                else:
                    self._reset(env_id)
            else:
                self._next_obs[env_id] = timestep[env_id].obs
        return timestep

    def seed(self, seed: List[int]) -> None:
        self._env_seed = seed

    def close(self) -> None:
        if self._closed:
            return
        self._env_ref.close()
        for env in self._envs:
            env.close()
        self._closed = True
