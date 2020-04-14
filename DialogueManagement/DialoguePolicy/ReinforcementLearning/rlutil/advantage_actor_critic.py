import abc
from typing import Dict, Any, NamedTuple

import torch

from DialogueManagement.DialoguePolicy.ReinforcementLearning.rlutil.dictlist import \
    DictList
from DialogueManagement.DialoguePolicy.ReinforcementLearning.rlutil.experience_memory import \
    ExperienceMemory


def flatten_parallel_rollout(d):
    return {
        k: flatten_parallel_rollout(v) if isinstance(v, dict) else flatten_array(v)
        for k, v in d.items()
    }


def flatten_array(v):
    return v.transpose(0, 1).reshape(v.shape[0] * v.shape[1], *v.shape[2:])


class EnvStep(NamedTuple):
    observation: torch.FloatTensor
    reward: torch.FloatTensor
    done: torch.LongTensor


class AgentStep(NamedTuple):
    actions: torch.LongTensor
    v_values: torch.FloatTensor


class EnvStepper:
    @abc.abstractmethod
    def step(self, agent_step: AgentStep) -> EnvStep:
        raise NotImplementedError

    @abc.abstractmethod
    def reset(self) -> EnvStep:
        raise NotImplementedError


class AgentStepper:
    @abc.abstractmethod
    def step(self, env_step: EnvStep) -> AgentStep:
        raise NotImplementedError


class Experience(NamedTuple):
    env_steps: EnvStep
    agent_steps: AgentStep
    advantages: torch.FloatTensor
    returnn: torch.FloatTensor


def generalized_advantage_estimation(
    rewards, values, dones, num_rollout_steps, discount, gae_lambda
):
    assert values.shape[0] == 1 + num_rollout_steps
    advantage_buffer = torch.zeros(rewards.shape[0] - 1, rewards.shape[1])
    next_advantage = 0
    for i in reversed(range(num_rollout_steps)):
        mask = torch.tensor((1 - dones[i + 1]), dtype=torch.float32)
        bellman_delta = rewards[i + 1] + discount * values[i + 1] * mask - values[i]
        advantage_buffer[i] = (
            bellman_delta + discount * gae_lambda * next_advantage * mask
        )
        next_advantage = advantage_buffer[i]
    return advantage_buffer


class A2CParams(NamedTuple):
    entropy_coef: float = 0.01
    value_loss_coef: float = 0.5
    max_grad_norm: float = 0.5
    num_rollout_steps: int = 4
    discount: float = 0.99
    lr: float = 1e-2
    gae_lambda: float = 0.95


def calc_loss(exps: Experience, w: World, p: A2CParams):
    dist, value = w.agent.calc_dist_value(exps.env_steps.observation)
    entropy = dist.entropy().mean()
    policy_loss = -(dist.log_prob(exps.agent_steps.actions) * exps.advantages).mean()
    value_loss = (value - exps.returnn).pow(2).mean()
    loss = policy_loss - p.entropy_coef * entropy + p.value_loss_coef * value_loss
    return loss


def gather_exp_via_rollout(
    env: EnvStepper, agent: AgentStepper, exp_mem: ExperienceMemory, num_rollout_steps
):
    for _ in range(num_rollout_steps):
        env_step = env.step(AgentStep(**exp_mem[exp_mem.last_written_idx].agent))
        agent_step = agent.step(env_step)
        exp_mem.store_single(
            DictList.build({"env": env_step._asdict(), "agent": agent_step._asdict()})
        )


def collect_experiences_calc_advantage(w: World, params: A2CParams) -> Experience:
    assert w.exp_mem.current_idx == 0
    w.exp_mem.last_becomes_first()

    gather_exp_via_rollout(w.env, w.agent, w.exp_mem, params.num_rollout_steps)
    assert w.exp_mem.last_written_idx == params.num_rollout_steps

    env_steps = w.exp_mem.buffer.env
    agent_steps = w.exp_mem.buffer.agent
    advantages = generalized_advantage_estimation(
        rewards=env_steps.reward,
        values=agent_steps.v_values,
        dones=env_steps.done,
        num_rollout_steps=params.num_rollout_steps,
        discount=params.discount,
        gae_lambda=params.gae_lambda,
    )
    return Experience(
        **{
            "env_steps": DictList(**flatten_parallel_rollout(env_steps[:-1])),
            "agent_steps": DictList(**flatten_parallel_rollout(agent_steps[:-1])),
            "advantages": flatten_array(advantages),
            "returnn": flatten_array(agent_steps[:-1].v_values + advantages),
        }
    )