import torch


def compute(next_value,reward,masks,values,gamma=0.99,lambda_=0.95):
    """
    计算GAE（Generalized Advantage Estimation）
    :param next_value:
    :param reward:
    :param masks:
    :param values:
    :param gamma:
    :param lambda_:
    :return:
        returns(Tensor):用于训练Critic的目标值（Target Value）
        advantages(Tensor):用于训练Actor的优势值。
    """
    values = values + [next_value] #把最后的value拼接到列表末尾方便计算
    gae = 0
    returns = []

    #从最后一步开始往前遍历
    for step in reversed(range(len(reward))):
        #1、计算TD Error(delta)
        delta = reward[step] + gamma * values[step + 1] * masks[step] - values[step]

        #2、递归计算GAE
        #A_t = delta + (gama * lambda) * A_{next}
        gae = delta + gamma * lambda_ * masks[step] * gae