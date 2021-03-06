import argparse
import os

import gym
from argument import *
import torch
import cv2
import numpy as np

from multiagent.environment import MultiAgentEnv
import multiagent.scenarios as scenarios

from agent_dir.MA_agent_ddpg import MA_DDPG
from agent_dir.MA_agent_VDN import MA_VDN
from agent_dir.MA_agent_QMIX import MA_QMIX

def parse():
    parser = argparse.ArgumentParser(description="SYSU_RL_HW2")
    parser.add_argument('--task', default='qmix', type=str, choices=['maddpg', 'vdn', 'qmix'], help='whether train policy gradient')

    parser.add_argument("--render", default=False, type=bool)
    parser.add_argument("--snap", default=10, type=float)
    parser.add_argument("--name", default='CartPole', type=str)
    parser.add_argument("--snap_save", default=10000, type=float)
    parser.add_argument("--save_dir", default='output', type=str)

    #parser = maddpg_arguments(parser)
    #parser = VDN_arguments(parser)
    parser = QMIX_arguments(parser)
    args = parser.parse_args()
    return args


def run(args):
    env_name = args.env_name
    scenario = scenarios.load(env_name).Scenario()
    world = scenario.make_world()
    # create multiagent environment
    env = MultiAgentEnv(world, scenario.reset_world, scenario.reward, scenario.observation,
                        shared_viewer=True)
    agent = eval(args.agent)(env, args)
    agent.run()

def test(args):
    env_name = args.env_name
    scenario = scenarios.load(env_name).Scenario()
    world = scenario.make_world()
    # create multiagent environment
    env = MultiAgentEnv(world, scenario.reset_world, scenario.reward, scenario.observation, info_callback=None,
                        shared_viewer=True)
    state=env.reset()

    print(env)
    print(env.action_space[0])
    print(env.observation_space[0].high)
    print(dir(env.observation_space[0]))
    print(state[0].shape)
    #print(env.observation_space)

    state = env.step([np.random.rand(5),np.random.rand(5),np.random.rand(5)])
    print(state)
    0/0

    #state=torch.tensor(state).permute(2,0,1)

    from matplotlib import pyplot as plt
    plt.figure()
    for i in range(3):
        plt.subplot(2,2,1+i)
        plt.imshow(state[i, :,:])
    plt.show()


if __name__ == '__main__':
    args = parse()
    args.save_dir = f'{args.save_dir}_{args.agent}'
    os.makedirs(os.path.join(args.save_dir, args.name), exist_ok=True)
    run(args)
