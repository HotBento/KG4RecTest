import os
import torch
import torch.multiprocessing as mp

from utils import parse_args
from eval import evaluate_kg, cold_start_evaluate
import false_experiment, size_experiment, cold_start_experiment, decrease_experiment

def run(args_queue:mp.Queue, device:torch.device):
    cnt = 0
    while True:
        args_dict = args_queue.get()
        if args_dict == None:
            print("{}_cnt:{}    break".format(device, cnt))
            break

        # Environment settings
        experiment      : str   = args_dict['experiment']
        dataset         : str   = args_dict['dataset']
        test_type       : str   = args_dict['test_type']
        rate            : float = args_dict['rate']
        eval_times      : int   = args_dict['eval_times'] 
        model_type_str  : str   = args_dict['model_type_str']
        topk            : list  = args_dict['topk']
        worker_num      : int   = args_dict['worker_num']
        metrics         : list  = args_dict['metrics']
        suffix = str(device).split(':')[-1]

        if experiment == 'false':
            run_once = false_experiment.run_once
        elif experiment == 'size':
            run_once = size_experiment.run_once
        elif experiment == 'coldstart':
            run_once = cold_start_experiment.run_once
        elif experiment == 'decrease':
            run_once = decrease_experiment.run_once
        else:
            raise NameError('Invalid experiment.')

        print("{}_cnt:{}    run".format(device, cnt))
        for i in range(eval_times):
            # Mutant dataset generation
            if experiment == 'coldstart':
                args_dict['ptr'] = i
            p = mp.Process(target=run_once, args=[args_dict, device])
            p.start()
            p.join()

            # Evaluation
            save_root = './result/{}/{}_experiment/{}_test'.format(dataset, experiment, test_type)
            if not os.path.exists(save_root):
                try:
                    os.makedirs(save_root)
                except:
                    pass
            save_path = os.path.join(save_root, '{}_{}.txt'.format(model_type_str, rate))
            fake_kg_path = '{}-fake{}'.format(dataset, suffix)

            if experiment == 'coldstart':
                save_path = os.path.join(save_root, '{}_{}_{}.txt'.format(model_type_str, rate, args_dict['cs_threshold']))
                p = mp.Process(target=cold_start_evaluate, args=[model_type_str, device, topk, save_path, fake_kg_path, metrics, worker_num])
            else:
                p = mp.Process(target=evaluate_kg, args=[model_type_str, device, topk, save_path, fake_kg_path, metrics, worker_num])
            p.start()
            p.join()
        cnt += 1
    return 0

if __name__ == '__main__':
    args = parse_args()
    queue = mp.Queue()
    offset = args.offset

    if args.experiment == 'coldstart':
        con1, con2 = mp.Pipe()
        all_test_users = []
        for i in range(args.eval_times):
            p = mp.Process(target=cold_start_experiment.generate_test_user_list,
                           args=[con1, args.dataset, args.test_user_ratio])
            p.start()
            all_test_users.append(con2.recv())
            # print(all_test_users[-1])
            p.join()
        con1.close()
        con2.close()


    for rate in args.rate:
        for test_type in args.test_type_list:
            for model_type_str in args.model:
                if os.path.exists('./result/{}/{}_experiment/{}_test/{}_{}.txt'\
                        .format(args.dataset, args.experiment, test_type, model_type_str, rate)):
                    continue
                if args.experiment == 'coldstart' and os.path.exists('./result/{}/{}_experiment/{}_test/{}_{}_{}.txt'\
                        .format(args.dataset, args.experiment, test_type, model_type_str, rate, args.cs_threshold)):
                    continue
                args_dict = dict()
                args_dict['experiment']             = args.experiment
                args_dict['dataset']                = args.dataset
                args_dict['test_type']              = test_type
                args_dict['rate']                   = rate
                args_dict['model_type_str']         = model_type_str
                args_dict['eval_times']             = args.eval_times
                args_dict['topk']                   = args.topk
                args_dict['worker_num']             = args.worker_num + offset
                args_dict['metrics']                = args.metrics
                if args.experiment == 'coldstart':
                    args_dict['all_test_users'] = all_test_users
                    args_dict['cs_threshold'] = args.cs_threshold
                    args_dict['test_user_ratio'] = args.test_user_ratio
                queue.put(args_dict)
    for i in range(args.worker_num):
        queue.put(None)
    process_list = []
    for i in range(offset,offset+args.worker_num):
        p = mp.Process(target=run, args=[queue, torch.device('cuda:'+str(i))])
        p.start()
        process_list.append(p)
    for p in process_list:
        p.join()
    print("Finished!")