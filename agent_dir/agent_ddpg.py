import os
import random
import copy
import numpy as np
import torch
from pathlib import Path
from tensorboardX import SummaryWriter
from torch import nn, optim
from agent_dir.agent import Agent
from copy import deepcopy
from .utils import *

from torchvision.models import resnet, alexnet, vgg
from loguru import logger

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

class ActorNetwork(nn.Module):
    def __init__(self, state_size, action_size):
        super(ActorNetwork, self).__init__()
        self.output_size=action_size

        self.net = nn.Sequential(
            nn.Linear(state_size, 512),
            nn.SiLU(),

            nn.Linear(512, 512),
            nn.SiLU(),

            nn.Linear(512, action_size),
            nn.Tanh()
        )

    def forward(self, inputs):
        return self.net(inputs)

class CriticNetwork(nn.Module):
    def __init__(self, state_size, action_size):
        super(CriticNetwork, self).__init__()
        #self.net = resnet.resnet18(pretrained=True)
        #self.net.conv1 = nn.Conv2d(4, self.net.conv1.out_channels, kernel_size=7, stride=2, padding=3, bias=False)
        #self.net.fc = nn.Linear(self.net.fc.in_features, output_size)

        #self.net = alexnet(pretrained=True)
        #self.net.features[0]=nn.Conv2d(4, 64, kernel_size=11, stride=4, padding=2)
        #self.net.classifier[-1]=nn.Linear(4096, output_size)

        self.base_state = nn.Sequential(
            nn.Linear(state_size, 512),
            nn.SiLU(),
        )

        self.base_act = nn.Sequential(
            nn.Linear(action_size, 512),
            nn.SiLU(),
        )

        self.net = nn.Sequential(
            nn.Linear(1024, 512),
            nn.SiLU(),

            nn.Linear(512, 256),
            nn.SiLU(),

            nn.Linear(256, 1)
        )

    def forward(self, inputs):
        return self.net(inputs)

class ReplayBuffer:
    def __init__(self, buffer_size):
        self.buffer = []
        self.buffer_size = buffer_size

    def __len__(self):
        return len(self.buffer)

    def proc(self, state, action, reward, next_state, done):
        return state.float(), action, reward, next_state.float(), done

    def push(self, *transition):
        if len(self.buffer)>=self.buffer_size:
            #self.buffer[random.randint(0,self.buffer_size-1)]=self.proc(*transition)
            self.buffer.pop(0)
            self.buffer.append(self.proc(*transition))
        else:
            self.buffer.append(self.proc(*transition))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        return [torch.stack(x, dim=0).to(device) for x in list(zip(*batch))]

    def clean(self):
        self.buffer.clear()


class AgentDQN(Agent):
    def __init__(self, env, args, network=QNetwork):
        """
        Initialize every things you need here.
        For example: building your model
        """
        super(AgentDQN, self).__init__(env)

        self.n_act = env.action_space.n

        self.Qnet = network(self.n_act).to(device)
        #self.Qnet = QNetworkCart(4, self.n_act).to(device)
        self.Qnet_T = deepcopy(self.Qnet).to(device)
        for m in self.Qnet_T.parameters():
            m.requires_grad=False

        self.mem = ReplayBuffer(args.buffer_size)
        self.eps = args.eps_start

        self.criterion = nn.MSELoss()
        self.optimizer = torch.optim.Adam(self.Qnet.parameters(), lr=args.lr)

        self.args=args
        self.writer = SummaryWriter("log")

        self.eps_scd = EpsScheduler(args.eps_start, args.eps_end, args.eps_decay)

    
    def init_game_setting(self):
        """

        Testing function will call this function at the begining of new game
        Put anything you want to initialize if necessary

        """
        ##################
        # YOUR CODE HERE #
        ##################
        pass

    def train_step(self, state, action, reward, next_state, done):
        y = deepcopy(reward)
        action = action.view(-1).unsqueeze(-1)

        with torch.no_grad():
            not_done = ~done
            y[not_done] += self.args.gamma*self.Qnet_T(next_state[not_done, ...]).max(dim=-1)[0]

        pred = self.Qnet(state).gather(1, action).view(-1)

        loss = self.criterion(pred, y)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()

    def train(self):
        """
        Implement your training algorithm here
        """
        n_ep=10000
        step = 0
        loss_sum = 0

        for episode in range(n_ep):
            ep_r = 0

            state = self.env.reset()
            state = torch.tensor(state, device=device)

            while True:
                if self.args.render:
                    self.env.render()

                action = self.make_action(state.unsqueeze(0).float(), self.args.test).detach().cpu()
                self.eps = self.eps_scd.step()

                next_state, reward, done, info = self.env.step(action.item())

                ep_r += reward

                self.mem.push(*[torch.tensor(x, device='cpu') for x in [state, action, reward, next_state, done]])

                if len(self.mem) >= self.args.batch_size*5:
                    if (step + 1) % self.args.target_update_freq == 0:
                        self.Qnet_T.load_state_dict(self.Qnet.state_dict())

                    trans = self.mem.sample(self.args.batch_size)
                    loss = self.train_step(*trans)

                    loss_sum += loss
                    if step%self.args.snap==0:
                        self.writer.add_scalar("loss", loss, global_step=step)
                        logger.info(f'[{episode}/{n_ep}] <{step}> loss:{loss_sum/self.args.snap}, eps:{self.eps}')
                        loss_sum = 0
                step += 1

                if done:# or step>self.args.n_frames:
                    self.writer.add_scalar("ep_r", ep_r, global_step=episode)
                    logger.info(f'[{episode}/{n_ep}] <{step}> ep_r:{ep_r}, len_mem:{len(self.mem)}, eps:{self.eps}')
                    break

                state = torch.tensor(next_state, device=device)

                if (step + 1) % self.args.snap_save == 0:
                    torch.save(self.Qnet.state_dict(), os.path.join(self.args.save_dir, self.args.name, f'net_{step + 1}.pth'))

    @torch.no_grad()
    def make_action(self, observation, test=True):
        """
        Return predicted action of your agent
        Input:observation
        Return:action
        """
        if test:
            return self.Qnet(observation).argmax(dim=-1)
        else:
            return self.Qnet(observation).argmax(dim=-1) if random.random()>self.eps else torch.randint(0,self.n_act,(1,))

    def run(self):
        """
        Implement the interaction between agent and environment here
        """
        self.train()
        self.writer.close()

class AgentDDQN(AgentDQN):
    def train_step(self, state, action, reward, next_state, done):
        y = deepcopy(reward)
        action = action.view(-1).unsqueeze(-1)

        with torch.no_grad():
            not_done = ~done
            Q_max_a = self.Qnet(next_state[not_done, ...]).max(dim=-1)[1].long().unsqueeze(-1)
            y[not_done] += self.args.gamma*self.Qnet_T(next_state[not_done, ...]).gather(1, Q_max_a).view(-1)

        pred = self.Qnet(state).gather(1, action).view(-1)

        loss = self.criterion(pred, y)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item()

class AgentDuelingDQN(AgentDQN):
    def __init__(self, env, args):
        super().__init__(env, args, network=DuelingQNetwork)