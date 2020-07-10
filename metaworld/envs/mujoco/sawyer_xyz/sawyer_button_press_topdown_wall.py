import numpy as np
from gym.spaces import Box

from metaworld.envs.env_util import get_asset_full_path
from metaworld.envs.mujoco.sawyer_xyz.base import SawyerXYZEnv


class SawyerButtonPressTopdownWallEnv(SawyerXYZEnv):
    hand_low = (-0.5, 0.40, 0.05)
    hand_high = (0.5, 1, 0.5)
    goal_low = hand_low
    goal_high = hand_high
    goal_space = Box(np.array(goal_low), np.array(goal_high))


    def __init__(self):

        obj_low = (-0.05, 0.8, 0.05)
        obj_high = (0.05, 0.9, 0.05)

        super().__init__(
            self.model_name,
            hand_low=self.hand_low,
            hand_high=self.hand_high,
        )

        self.random_init = False

        self.init_config = {
            'obj_init_pos': np.array([0, 0.8, 0.05], dtype=np.float32),
            'hand_init_pos': np.array([0, 0.6, 0.2], dtype=np.float32),
        }
        self.goal = np.array([0, 0.88, 0.1])
        self.obj_init_pos = self.init_config['obj_init_pos']
        self.hand_init_pos = self.init_config['hand_init_pos']


        self.max_path_length = 150

        self.action_space = Box(
            np.array([-1, -1, -1, -1]),
            np.array([1, 1, 1, 1]),
        )

        self.obj_and_goal_space = Box(
            np.array(obj_low),
            np.array(obj_high),
        )
        self.observation_space = Box(
            np.hstack((self.hand_low, obj_low,)),
            np.hstack((self.hand_high, obj_high,)),
        )

        self._freeze_rand_vec = False
        self.reset()
        self._freeze_rand_vec = True

    @property
    def model_name(self):
        return get_asset_full_path('sawyer_xyz/sawyer_button_press_topdown_wall.xml')

    def step(self, action):
        self.set_xyz_action(action[:3])
        self.do_simulation([action[-1], -action[-1]])
        # The marker seems to get reset every time you do a simulation
        ob = self._get_obs()
        obs_dict = self._get_obs_dict()
        reward, reachDist, pressDist = self.compute_reward(action, obs_dict)
        self.curr_path_length +=1
        info = {'reachDist': reachDist, 'goalDist': pressDist, 'epRew': reward, 'pickRew':None, 'success': float(pressDist <= 0.02)}
        info['goal'] = self.goal

        return ob, reward, False, info

    def _get_obs(self):
        hand = self.get_endeff_pos()
        objPos =  self.data.site_xpos[self.model.site_name2id('buttonStart')]
        flat_obs = np.concatenate((hand, objPos))

        return np.concatenate([flat_obs,])

    def _get_obs_dict(self):
        hand = self.get_endeff_pos()
        objPos =  self.data.site_xpos[self.model.site_name2id('buttonStart')]
        flat_obs = np.concatenate((hand, objPos))
        return dict(
            state_observation=flat_obs,
            state_desired_goal=self._state_goal,
            state_achieved_goal=objPos,
        )

    def _set_obj_xyz(self, pos):
        qpos = self.data.qpos.flat.copy()
        qvel = self.data.qvel.flat.copy()
        qpos[9] = pos
        qvel[9] = 0
        self.set_state(qpos, qvel)

    def reset_model(self):
        self._reset_hand()
        self._state_goal = self.goal.copy()

        if self.random_init:
            goal_pos = self._get_state_rand_vec()
            self.obj_init_pos = goal_pos
            button_pos = goal_pos.copy()
            button_pos[1] += 0.08
            button_pos[2] += 0.07
            self._state_goal = button_pos

        self.sim.model.body_pos[self.model.body_name2id('box')] = self.obj_init_pos
        self.sim.model.body_pos[self.model.body_name2id('button')] = self._state_goal
        self._set_obj_xyz(0)
        self._state_goal = self.get_site_pos('hole')
        self.maxDist = np.abs(self.data.site_xpos[self.model.site_name2id('buttonStart')][2] - self._state_goal[2])
        self.target_reward = 1000*self.maxDist + 1000*2

        return self._get_obs()

    def _reset_hand(self):
        for _ in range(10):
            self.data.set_mocap_pos('mocap', self.hand_init_pos)
            self.data.set_mocap_quat('mocap', np.array([1, 0, 1, 0]))
            self.do_simulation([-1,1], self.frame_skip)

        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        self.init_fingerCOM  =  (rightFinger + leftFinger)/2
        self.pickCompleted = False

    def compute_reward(self, actions, obs):
        del actions

        if isinstance(obs, dict):
            obs = obs['state_observation']

        objPos = obs[3:6]

        rightFinger, leftFinger = self.get_site_pos('rightEndEffector'), self.get_site_pos('leftEndEffector')
        fingerCOM  =  (rightFinger + leftFinger)/2

        pressGoal = self._state_goal[2]

        pressDist = np.abs(objPos[2] - pressGoal)
        reachDist = np.linalg.norm(objPos - fingerCOM)
        reachRew = -reachDist

        c1 = 1000
        c2 = 0.01
        c3 = 0.001
        if reachDist < 0.05:
            pressRew = 1000*(self.maxDist - pressDist) + c1*(np.exp(-(pressDist**2)/c2) + np.exp(-(pressDist**2)/c3))
        else:
            pressRew = 0
        pressRew = max(pressRew, 0)
        reward = reachRew + pressRew

        return [reward, reachDist, pressDist]
