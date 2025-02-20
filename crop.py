import argparse
import os
import os.path as osp

import numpy as np
import ray
import yaml
from PIL import Image

from fundus_circle_cropping import fundus_cropping, utils

parser = argparse.ArgumentParser()
parser.add_argument("-c", "--cfg", type=str, help="Path to config file.")


if __name__ == "__main__":

    failures = []

    # Load config from yaml file.
    args = parser.parse_args()
    yaml_path = os.path.join(args.cfg)
    with open(yaml_path) as f:
        cfg = yaml.safe_load(f)

    # Create folders in case they are not already existing.
    utils.create_folder(osp.join(cfg["root_folder"], cfg["image_folder"]))
    if not cfg["minimal_save"]:
        utils.create_folder(osp.join(cfg["root_folder"], cfg["mask_folder"]))

    # Data folder and ids.
    data_folder = osp.join(cfg["root_folder"], cfg["data_folder"])

    with open(cfg["ids_file"], "r") as f:
        list_files = f.read().split("\n")

    if cfg["minimal_save"]:
        id_to_ratios_mask = {}

    if cfg["parallel_processing"]:
        # MSA's additions for parallel processing
        num_workers = os.cpu_count() - cfg["num_workers_reverse"]
        print(f"Number of workers : {num_workers}")
        ray.init(num_cpus=num_workers)
        assert ray.is_initialized()

        remote_fundus_cropping = ray.remote(fundus_cropping.fundus_image)
        # Start tasks in parallel.
        futures = [
            remote_fundus_cropping.remote(
                x=np.array(
                    Image.open(
                        osp.join(
                            data_folder, f"{x_id}.{cfg['file_extension_data_in']}"
                        ),
                    ),
                ),
                x_id=x_id,
                image_folder=osp.join(cfg["root_folder"], cfg["image_folder"]),
                file_extension=cfg["file_extension_data_out"],
                mask_folder=osp.join(cfg["root_folder"], cfg["mask_folder"]),
                resize_shape=cfg["resize_shape"],
                resize_canny_edge=cfg["resize_canny_edge"],
                sigma_scale=cfg["sigma_scale"],
                circle_fit_steps=cfg["circle_fit_steps"],
                # λ=cfg["λ"],
                remove_rectangles=cfg["remove_rectangles"],
                minimal_save=cfg["minimal_save"],
            )
            for x_id in list_files
        ]

        results = ray.get(futures)

        for result_idx, result in enumerate(results):
            if result[1]:  # failure
                failures.append(list_files[result_idx])
            if cfg["minimal_save"]:
                id_to_ratios_mask[list_files[result_idx]] = result[0]

        ray.shutdown()
        assert not ray.is_initialized()

    else:
        for id in list_files:
            print(f"Crop and save image mask of {id}.\n")
            # Load image.
            x = np.array(
                Image.open(
                    osp.join(data_folder, f"{id}.{cfg['file_extension_data_in']}")
                )
            )
            ratios, failure = fundus_cropping.fundus_image(
                x=x,
                x_id=id,
                image_folder=osp.join(cfg["root_folder"], cfg["image_folder"]),
                file_extension=cfg["file_extension_data_out"],
                mask_folder=osp.join(cfg["root_folder"], cfg["mask_folder"]),
                resize_shape=cfg["resize_shape"],
                resize_canny_edge=cfg["resize_canny_edge"],
                sigma_scale=cfg["sigma_scale"],
                circle_fit_steps=cfg["circle_fit_steps"],
                # λ=cfg["lamda"],
                remove_rectangles=cfg["remove_rectangles"],
                minimal_save=cfg["minimal_save"],
            )
            if failure:
                failures.append(id)
            if cfg["minimal_save"]:
                id_to_ratios_mask[id] = ratios

    # Save file names of failure images.
    with open(
        osp.join(cfg["root_folder"], cfg["image_folder"], "failures.lst"),
        "w",
    ) as f:
        f.write("\n".join(failures))

    # Save mask ratios.
    if cfg["minimal_save"]:
        with open(
            osp.join(cfg["root_folder"], f"{cfg['mask_ratios']}.yml"), "w"
        ) as outfile:
            yaml.dump(id_to_ratios_mask, outfile)
