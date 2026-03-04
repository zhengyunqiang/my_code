import gym
from gym import spaces
import numpy as np
import torch

num_bases = 2        # 基站数量
num_cars = 2         # 车厢数量
users_count = 10       # 每个车厢的用户数量
num_subchannels = 5  # 子信道数量
coverage = 250       # 基站覆盖范围
speed = 10           # 车厢的速度
max_power=100        # 最大功率
B_TBS = 10           # 带宽
delta_0 = 1e-9       # 噪声功率密度 (W/Hz)
K = 1                # 信道增益常量
gamma = 2            # 距离衰减指数
times = 0.01         # 时隙持续时间
max_rate=100         # 最大速率
mean_demand = 8     #数据均值
std_dev_demand = 3  #数据方差

base_locations = np.array([250, 750])  # 基站初始位置
car_positions = np.array([-i * 30  for i in range(num_cars)], dtype=float)  # 初始化车厢初始位置

class CarriageEnv(gym.Env):
    def __init__(self, base_station_env, users_count, max_rate):
        super(CarriageEnv, self).__init__()

        #初始化基本信息
        self.base_station_env = base_station_env  # 引用基站环境实例
        self.users_count = users_count
        self.max_rate = max_rate
        self.distances_to_stations = np.abs(car_positions[:, None] - base_locations)

        # 初始化每个用户的数据量
        self.initial_data_per_user = np.full((users_count,), fill_value=50, dtype=np.float32)
        self.total_initial_data = np.sum(self.initial_data_per_user)

        # 定义车厢智能体的状态空间
        self.observation_space = spaces.Dict({
            'remaining_data': spaces.Box(low=0, high=self.total_initial_data, shape=(num_cars,), dtype=np.float32),
            'car_positions': spaces.Box(low=-np.inf, high=np.inf, shape=(num_cars,), dtype=np.float32),
            'distances_to_stations': spaces.Box(low=0, high=np.inf, shape=(num_cars, num_bases), dtype=np.float32),
            'coverage_status': spaces.MultiBinary(num_cars * num_bases),
            'user_base_selection': spaces.MultiDiscrete([num_bases] * num_cars * users_count)
        })

        # 定义动作空间：基站选择
        self.action_space = spaces.MultiDiscrete([num_bases] * users_count)

        self.reset()

    def reset(self):
        # 初始化车车厢数据剩余量
        self.remaining_data = np.full((num_cars,), fill_value=self.total_initial_data, dtype=np.float32)

        self.distances_to_stations = np.abs(car_positions[:, None] - base_locations)

        # 初始化用户基站选择矩阵，假设-1表示未选择任何基站
        self.user_base_selection = np.full((num_cars, self.users_count), -1, dtype=np.int32)

        # 初始化覆盖状态二维数组
        self.coverage_status = np.zeros((num_cars, num_bases), dtype=np.int32)

        # 根据距离判断每个车厢是否在每个基站的覆盖范围内
        for i in range(num_cars):
            for j in range(num_bases):
                if self.distances_to_stations[i, j] <= coverage:
                    self.coverage_status[i, j] = 1

        self.car_positions = np.array([-i * 30 for i in range(num_cars)], dtype=float)  # 初始化车厢初始位置

        self.state = {
            'remaining_data': self.remaining_data,
            'distances_to_stations': self.distances_to_stations.flatten(),
            'coverage_status': self.coverage_status.flatten(),
            'car_positions': self.car_positions,
            'user_base_selection': self.user_base_selection.flatten()  # 这里也扁平化
        }
        return self.state

    def step(self, carriage_index, action):
        # 保存当前状态
        current_state = {
            'car_positions': self.car_positions,
            'distances_to_stations': self.distances_to_stations.flatten(),
            'remaining_data': self.remaining_data,
            'coverage_status': self.coverage_status.flatten(),
            'user_base_selection': self.user_base_selection.flatten()
        }

        # 更新状态
        self.car_positions += speed  # 更新车厢位置
        self.distances_to_stations = np.abs(self.car_positions[:, None] - base_locations)  # 更新车厢到基站的距离

        # 从基站环境中获取subchannel_allocations和subchannel_rate
        subchannels_allocation = self.base_station_env.subchannel_allocations
        subchannels_rate = self.base_station_env.subchannel_rate

        # 计算车厢的外部速率
        total_rate_per_car = self.calculate_total_rate_per_car(subchannels_allocation, subchannels_rate, num_cars)


        # 更新剩余数据量
        rate = total_rate_per_car[carriage_index]
        self.remaining_data -= rate * times

        # 更新覆盖范围
        self.coverage_status = np.zeros((num_cars, num_bases), dtype=np.int32)
        for i in range(num_cars):
            for j in range(num_bases):
                if self.distances_to_stations[i, j] <= coverage:
                    self.coverage_status[i, j] = 1

        # 更新指定车厢的用户基站选择矩阵的对应行
        self.user_base_selection[carriage_index, :] = action

        # 判断是否结束
        done = np.all(self.remaining_data <= 0)

        # 返回下一个状态和当前状态
        next_state = {
            'remaining_data': self.remaining_data,
            'distances_to_stations': self.distances_to_stations.flatten(),
            'coverage_status': self.coverage_status.flatten(),
            'car_positions': self.car_positions,
            'user_base_selection': self.user_base_selection.flatten()
        }
        # print('++++++++++++++++++++++++++')
        # print(convert_node_state_to_feature_vector(next_state))
        # print('++++++++++++++++++++++++++')
        reward = None
        info = {}  # 可选的额外信息
        return next_state, reward, done, info

    def calculate_total_rate_per_car(self, subchannel_allocations, subchannel_rates, num_cars):
        """
        计算每个车厢的外部总速率。

        参数:
        subchannel_allocations (np.ndarray): 子信道分配矩阵，形状为 (num_bases, num_subchannels)。
        subchannel_rates (np.ndarray): 子信道速率矩阵，形状为 (num_bases, num_subchannels)。
        num_cars (int): 车厢的数量。

        返回:
        np.ndarray: 每个车厢的外部总速率数组，形状为 (num_cars,)。
        """
        # 初始化每个车厢的总速率
        total_rate_per_car = np.zeros(num_cars)

        # 获取基站数量和子信道数量
        num_bases, num_subchannels = subchannel_allocations.shape

        # 遍历子信道分配矩阵，计算每个车厢的外部总速率
        for base_index in range(num_bases):
            for subchannel_index in range(num_subchannels):
                car_index = subchannel_allocations[base_index, subchannel_index]
                total_rate_per_car[car_index] += subchannel_rates[base_index, subchannel_index]

        return total_rate_per_car



class BaseStationEnv(gym.Env):
    def __init__(self, num_subchannels, max_power):
        super(BaseStationEnv, self).__init__()

        self.subchannel_rate = np.zeros((num_bases, num_subchannels), dtype=np.float32)
        self.distances_to_stations = np.abs(car_positions[:, None] - base_locations)
        self.distances_to_cars = self.distances_to_stations.T
        self.num_subchannels = num_subchannels
        self.max_power = max_power

        # 初始化基站连接状态空间
        self.subchannel_allocations = np.zeros((num_bases, num_subchannels), dtype=np.int32)
        self.current_powers = np.zeros((num_bases, num_subchannels), dtype=np.float32)
        self.data_throughput = np.zeros(num_bases, dtype=np.float32)
        self.car_positions = np.array([-i * 30 for i in range(num_cars)], dtype=float)
        self.distances_to_cars = np.zeros((num_bases, num_cars), dtype=np.float32)
        self.subchannel_power = np.zeros((num_bases, num_subchannels), dtype=np.float32)

        # 定义基站智能体的状态空间
        self.observation_space = spaces.Dict({
            'subchannel_allocations': spaces.MultiDiscrete([num_cars] * num_bases * num_subchannels ),
            'current_powers': spaces.Box(low=0, high=max_power, shape=(num_subchannels * num_bases,), dtype=np.float32),
            'data_throughput': spaces.Box(low=0, high=np.inf, shape=(num_bases,), dtype=np.float32),
            'car_positions': spaces.Box(low=-np.inf, high=np.inf, shape=(num_cars,), dtype=np.float32),
            'distances_to_cars': spaces.Box(low=0, high=np.inf, shape=(num_bases, num_cars), dtype=np.float32),
            'subchannel_power': spaces.Box(low=0, high=np.inf, shape=(num_bases, num_subchannels), dtype=np.float32)
        })

        # 定义动作空间：子信道分配和功率分配
        self.action_space = spaces.Tuple((
            spaces.MultiDiscrete([num_cars] * num_subchannels),  # 子信道分配
            spaces.Box(low=0, high=max_power, shape=(num_subchannels,), dtype=np.float32)  # 功率分配
        ))

        self.reset()

    def reset(self):
        self.distances_to_stations = np.abs(car_positions[:, None] - base_locations)
        # 初始化环境并返回初始状态

        self.car_positions = np.array([-i * 30 for i in range(num_cars)], dtype=float)
        self.distances_to_cars = self.distances_to_stations.T
        self.subchannel_allocations = np.zeros((num_bases, num_subchannels), dtype=np.int32)
        self.current_powers = np.zeros((num_bases, num_subchannels), dtype=np.float32)
        self.data_throughput = np.zeros(num_bases, dtype=np.float32)

        self.state = {
            'car_positions': self.car_positions,
            'distances_to_cars': self.distances_to_cars.flatten(),
            'subchannel_allocations': self.subchannel_allocations.flatten(),
            'current_powers': self.current_powers.flatten(),
            'data_throughput': self.data_throughput,
        }
        return self.state

    def step(self, base_index, action):
        # 计算当前状态的Critic值和下一个状态的Critic值
        current_state = {
            'car_positions': self.car_positions,
            'distances_to_cars': self.distances_to_cars.flatten(),
            'subchannel_allocations': self.subchannel_allocations.flatten(),
            'current_powers': self.current_powers.flatten(),
            'data_throughput': self.data_throughput,
        }

        # 执行动作并返回下一个状态、奖励、完成标志和额外信息
        subchannel_action, power_action = action

        # 更新状态中的子信道分配和功率分配矩阵对应的行
        self.subchannel_allocations[base_index] = subchannel_action
        self.current_powers[base_index] = power_action

        # 调用计算信道增益的方法
        channel_gain_matrix = self.calculate_channel_gain_matrix(self.subchannel_allocations,self.distances_to_cars,K,gamma,epsilon = 1e-6 )

        #计算子信道的速率
        self.subchannel_rate = self.calculate_data_rate(B_TBS, self.current_powers, channel_gain_matrix, delta_0, self.subchannel_allocations)

        #更新每一个基站的外部总速率
        self.data_throughput = np.sum(self.subchannel_rate,axis = 1)
        # 更新车厢位置和距离
        self.car_positions += speed  # 更新车厢位置
        self.distances_to_stations = np.abs(self.car_positions[:, None] - base_locations)  # 更新车厢到基站的距离
        self.distances_to_cars = self.distances_to_stations.T   #更新每个基站到车厢的距离

        # 构造下一个状态
        next_state = {
            'car_positions': self.car_positions,
            'distances_to_cars': self.distances_to_cars.flatten(),
            'subchannel_allocations': self.subchannel_allocations.flatten(),
            'current_powers': self.current_powers.flatten(),
            'data_throughput': self.data_throughput
        }

        # 计算奖励为Critic值之差
        reward = None
        done = False  # 示例中的完成标志，实际中根据具体条件判断
        info = {}  # 可选的额外信息

        return next_state, reward, done, info

    def calculate_channel_gain_matrix(self, subchannel_allocations,distances_to_cars,K,gamma,epsilon = 1e-6 ):
        """
        计算信道增益矩阵
        :param subchannel_allocations: 几钻分配的子信道矩阵，形状为（num_bases,num_subchannels）
        :param distances_to_cars:基站到车厢的距离矩阵，形状为（num_bases,num_cars）
        :param K:信道增益计算的常数
        :param gamma:路径损耗指数
        :param epsilon:防止除以零的一个小常数
        :return:
        """

        num_bases, num_subchannels = subchannel_allocations.shape

        # 初始化信道增益矩阵
        channel_gain_matrix = np.zeros((num_bases, num_subchannels))
        # 计算信道增益矩阵
        for base_index in range(num_bases):
            for subchannel_index in range(num_subchannels):
                car = subchannel_allocations[base_index, subchannel_index]
                distance = distances_to_cars[base_index, car] + epsilon
                gain = K / (distance ** gamma)
                channel_gain_matrix[base_index, subchannel_index] = gain

        return channel_gain_matrix

    def calculate_data_rate(self,B_TBS, power_matrix, channel_gain_matrix, delta_0, subchannel_allocations):
        """
        计算每个基站和子信道组合的数据速率。

        参数:
        B_TBS (float): 每个子信道的带宽。
        power_matrix (np.ndarray): 功率矩阵，表示每个基站在每个子信道上的功率。
        channel_gain_matrix (np.ndarray): 信道增益矩阵，表示每个基站在每个子信道上的信道增益。
        delta_0 (float): 噪声功率密度。
        subchannel_allocations (np.ndarray): 子信道分配矩阵，表示每个基站在每个子信道上的分配情况（车厢编号）。

        返回:
        np.ndarray: 数据速率矩阵，形状与 channel_gain_matrix 相同。
        """
        num_bases, num_subchannels = subchannel_allocations.shape
        data_rates = np.zeros_like(channel_gain_matrix)

        for base_index in range(num_bases):
            for subchannel_index in range(num_subchannels):
                car = subchannel_allocations[base_index][subchannel_index]
                if car >= 0:  # 假设 -1 表示未分配的子信道
                    # 计算干扰
                    interference = 0
                    for other_base_index in range(num_bases):
                        if other_base_index != base_index:
                            other_car = subchannel_allocations[other_base_index][subchannel_index]
                            if other_car >= 0:
                                interference += power_matrix[other_base_index, subchannel_index] * channel_gain_matrix[
                                    other_base_index, subchannel_index]

                    # 计算信噪比 (SNR)
                    snr = (power_matrix[base_index, subchannel_index] * channel_gain_matrix[
                        base_index, subchannel_index]) / (
                                  interference + B_TBS * delta_0)

                    # 计算数据速率
                    data_rate = B_TBS * np.log2(1 + snr)
                    data_rates[base_index, subchannel_index] = data_rate

        return data_rates


def convert_node_state_to_feature_vector(node_state):
    """
    将节点的状态信息转换为节点的特征向量格式。

    参数：
    - node_state: dict，包含节点状态信息。

    返回：
    - feature_vector: torch.Tensor，节点的特征向量。
    """
    feature_list = []

    # 遍历节点状态字典中的每个键值对
    for key, value in node_state.items():
        # 将 numpy 数组或列表转换为 torch.Tensor，并展平成一维
        if isinstance(value, np.ndarray):
            tensor_value = torch.tensor(value.flatten(), dtype=torch.float32)
        elif isinstance(value, list):
            tensor_value = torch.tensor(np.array(value).flatten(), dtype=torch.float32)
        elif isinstance(value, torch.Tensor):
            tensor_value = value.flatten().float()
        else:
            # 对于单个数值，直接转换为张量
            tensor_value = torch.tensor([value], dtype=torch.float32)
        feature_list.append(tensor_value)

    # 将所有特征拼接成一个特征向量
    feature_vector = torch.cat(feature_list, dim=0)
    return feature_vector

