# -*- coding: utf-8 -*-

"""
@Author  : captain
@time    : 18-7-10 下午8:42
@ide     : PyCharm  
"""

import torch
import time
import torch.nn.functional as F
import models
import util
from config import DefaultConfig
import os
import datetime
from models.TextCNN import TextCNN
from sklearn import metrics
from torch.nn.utils import clip_grad_norm_
import numpy as np

best_score = 0.0


def main(**kwargs):
    args = DefaultConfig()
    if not torch.cuda.is_available():
        args.cuda = False
        args.device = None

    train_iter, val_iter, args.vocab_size, vectors = util.load_data(args, args.text_type)

    args.print_config()

    global best_score

    # 模型保存位置
    if not os.path.exists(args.save_dir):
        os.mkdir(args.save_dir)
    save_path = os.path.join(args.save_dir, '{}_{}.pth.tar'.format(args.model, args.id))

    # model
    model = getattr(models, args.model)(args, vectors)

    if args.cuda:
        torch.cuda.set_device(args.device)
        model.cuda()

    # 目标函数和优化器
    criterion = F.cross_entropy
    lr1, lr2 = args.lr1, args.lr2
    optimizer = model.get_optimizer(lr1, lr2, args.weight_decay)

    for i in range(args.epochs):
        total_loss = 0.0
        correct = 0
        total = 0

        model.train()

        for idx, batch in enumerate(train_iter):
            # 训练模型参数
            # 使用BatchNorm层时，batch size不能为1
            if len(batch) == 1:
                continue
            text, label = batch.text, batch.label
            if args.cuda:
                text, label = text.cuda(), label.cuda()

            optimizer.zero_grad()
            pred = model(text)
            loss = criterion(pred, label)
            loss.backward()
            # gradient clipping 梯度裁剪
            # 添加BN之后就没必要添加梯度裁剪
            # total_norm = clip_grad_norm_(model.parameters(), 10)
            # if total_norm > 10:
            #     print("clipping gradient: {} with coef {}".format(total_norm, 10 / total_norm))
            optimizer.step()

            # 更新统计指标
            total_loss += loss.item()
            predicted = pred.max(1)[1]
            total += label.size(0)
            correct += predicted.eq(label).sum().item()

            if idx % 20 == 19:
                print('[{}, {}] loss: {:.3f} | Acc: {:.3f}%({}/{})'.format(i + 1, idx + 1, total_loss / 20,
                                                                           100. * correct / total, correct, total))
                total_loss = 0.0

        f1score = val(model, val_iter, args)
        if f1score > best_score:
            best_score = f1score
            checkpoint = {
                'state_dict': model.state_dict(),
                'f1score': f1score,
                'epoch': i + 1,
                'config': args,
                'optimizer': optimizer
            }
            torch.save(checkpoint, save_path)
            print('Best tmp model f1score: {}'.format(best_score))
        if f1score < best_score:
            if lr1 < args.min_lr:
                print('* training over, best f1 score: {}'.format(best_score))
                break
            model.load_state_dict(torch.load(save_path)['state_dict'])
            lr1 *= 0.8
            lr2 = 2e-4 if lr2 == 0 else lr2 * 0.8
            optimizer = model.get_optimizer(lr1, lr2, args.weight_decay)
            print('* load previous best model: {}'.format(best_score))
            print('* model lr:{}  emb lr:{}'.format(lr1, lr2))


def val(model, dataset, args):
    # 计算模型在验证集上的分数

    # 将模型设为验证模式
    model.eval()

    acc_n = 0
    val_n = 0
    predict = np.zeros((0,), dtype=np.int32)
    gt = np.zeros((0,), dtype=np.int32)
    with torch.no_grad():
        for batch in dataset:
            text, label = batch.text, batch.label
            if args.cuda:
                text, label = text.cuda(), label.cuda()
            outputs = model(text)
            pred = outputs.max(1)[1]
            acc_n += (pred == label).sum().item()
            val_n += label.size(0)
            predict = np.hstack((predict, pred.cpu().numpy()))
            gt = np.hstack((gt, label.cpu().numpy()))

    acc = 100. * acc_n / val_n
    f1score = np.mean(metrics.f1_score(predict, gt, average=None))
    print('* Test Acc: {:.3f}%({}/{}), F1 Score: {}'.format(acc, acc_n, val_n, f1score))
    return f1score


if __name__ == '__main__':
    main()
