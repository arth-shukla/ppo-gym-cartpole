import gym
from gym import Env
from gym.wrappers import RecordVideo
import numpy as np
from ppo import PPOAgent
from tqdm import tqdm
import torch
import os
from pathlib import Path
import cv2

def train(env: Env, batch_size=5, num_epochs=4, lr=0.0003, num_games=300, learn_every=20, print_every=20, max_score=10000):

    # create agent (note this is done in train because it needs hyperparams)
    agent = PPOAgent(num_actions=env.action_space.n, 
                     batch_size=batch_size, lr=lr, 
                     num_epochs=num_epochs, 
                     input_dims=env.observation_space.shape)
    
    # lists to log score and avg score hist during training
    score_hist = []
    avg_score_hist = []

    # data tracking
    avg_score = 0
    num_steps = 0

    # init best score (used to see if model should be saved)
    best_score = env.reward_range[0]

    # num_games is the number of games to play, where each game ends
    # when the agent meets terminal conditions for the env
    for i in range(num_games):

        obs = env.reset()[0]
        done = False
        score = 0

        # run loop where model gathers data for "learn_every"
        # steps then learns using that information
        while not done:

            # choose action (actor)
            action, prob, val = agent.choose_action(obs)

            # get results of action
            next_obs, reward, done, _, _ = env.step(action)

            # save data to memory for experience learning
            agent.remember(obs, action, prob, val, reward, done)

            # learn using "learn_every" many memories
            if num_steps % learn_every == 0:
                agent.learn()
                agent.clear_memory()
            
            # update obs and tracking vars
            obs = next_obs
            score += reward
            num_steps += 1

            if score > max_score:
                print(f'Agent was too powerful! Score exceeded {max_score}')
                agent.save_models()

                score_hist.append(max_score)
                avg_score = np.mean(score_hist[-100:])
                avg_score_hist.append(avg_score)

                return agent, score_hist, avg_score_hist, i
            
        score_hist.append(score)

        # calc running avg score (use prev 100 so that
        # it's not biased by (a) lucky run(s))
        try:
            avg_score = np.mean(score_hist[-100:])
        except:
            avg_score = 0

        # track history
        avg_score_hist.append(avg_score)
        
        # save best model so far
        if avg_score > best_score:
            best_score = avg_score
            agent.save_models(silent=True)

        if i % print_every == 0 or i == num_games-1:
            print(f'game: [{i+1}/{num_games}]\tscore:\t{score:.2f}\tavg_score: {avg_score:.2f}')
    
    return agent, score_hist, avg_score_hist, num_games

def run_example(env: Env, agent: PPOAgent, max_score=1000):
    with torch.no_grad():
        obs = env.reset()[0]
        done = False
        score = 0

        # run loop where model gathers data for "learn_every"
        # steps then learns using that information
        while not done:

            # choose action (actor)
            action, prob, val = agent.choose_action(obs)

            # get results of action
            next_obs, reward, done, _, _ = env.step(action)

            # save data to memory for experience learning
            agent.remember(obs, action, prob, val, reward, done)
            
            # update obs and tracking vars
            obs = next_obs
            score += reward

            if score > max_score:
                print(f'Agent was too powerful! Score exceeded {max_score}')
                return


if __name__ == '__main__':

    SAVE_LOC = 'recordings/gym-cartpole-v1'

    # OpenAI Gym Cartpole for Testing
    env = gym.make('CartPole-v1', render_mode='rgb_array')

    # record and run train loop
    train_env = RecordVideo(env, SAVE_LOC, name_prefix='ppo-cartpole-train')
    trained_agent, score_hist, avg_score_hist, num_episodes = train(train_env, print_every=1)
    train_env.close()

    # load best model
    trained_agent.load_models()

    # record and run test example
    test_env = RecordVideo(env, SAVE_LOC, name_prefix='ppo-cartpole-test', episode_trigger= lambda x : x == 0)
    run_example(test_env, trained_agent)
    test_env.close()

    vids = dict()
    test_file = None
    for file in os.listdir(SAVE_LOC):
        file = Path(file)
        if file.suffix == '.mp4':
            if 'test' in file.stem:
                vids[num_episodes] = str(Path(SAVE_LOC) / file)
            else:
                episode_num = file.stem.split('-')[4]
                vids[int(episode_num)] = str(Path(SAVE_LOC) / file)

    import wandb

    wandb.login()

    run = wandb.init(project='PPO Gym Cart Pole')

    for score, avg_score in zip(score_hist, avg_score_hist):
        wandb.log({ 'Score': score, 'Average Score (Past 100 Episodes)': avg_score })
    for key in sorted(vids.keys()):
        wandb.log({f'PPO {key} Episodes': wandb.Video(vids[key], fps=24, format='mp4')})

    wandb.finish()
