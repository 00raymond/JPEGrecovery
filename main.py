import os
import pytsk3
import sys
import struct

JPEG_HEADER = b'\xFF\xD8'
JPEG_FOOTER = b'\xFF\xD9'

def find_unallocated_clusters(img_info, fs_info):
    allocated_clusters = set()
    unallocated_clusters = set()

    # Get the root directory inode
    root_directory = fs_info.open_dir(inode=fs_info.root_inode)

    # Iterate through all files in the file system
    for file in root_directory:
        try:
            for attr in file:
                if attr.info.meta and attr.info.meta.addr:
                    for run in attr.runs:
                        # Add all allocated clusters to the set
                        allocated_clusters.update(range(run.addr, run.addr + run.len))
        except IOError as e:
            print(f"Error while processing file: {e}")

    # Find the unallocated clusters by comparing the total number of clusters
    # with the set of allocated clusters
    total_clusters = fs_info.block_count_act()
    all_clusters = set(range(total_clusters))
    unallocated_clusters = all_clusters.difference(allocated_clusters)

    return list(unallocated_clusters)



def find_jpegs(img_info, fs_info, cluster, cluster_size):
    offset = fs_info.cluster_to_block(cluster) * fs_info.block_size
    img_info.seek(offset)
    data = img_info.read(cluster_size)

    jpegs = []
    start_index = 0

    while True:
        header_index = data.find(JPEG_HEADER, start_index)
        if header_index == -1:
            break

        footer_index = data.find(JPEG_FOOTER, header_index)
        if footer_index == -1:
            break

        jpegs.append((header_index + offset, footer_index + offset + len(JPEG_FOOTER)))
        start_index = footer_index + len(JPEG_FOOTER)

    return jpegs

def recover_jpegs(img_info, jpegs, output_directory):
    for i, (start_offset, end_offset) in enumerate(jpegs):
        img_info.seek(start_offset)
        data = img_info.read(end_offset - start_offset)

        output_file = os.path.join(output_directory, f'recovered_{i}.jpg')
        with open(output_file, 'wb') as f:
            f.write(data)

def main():
    # User input for device path and output directory
    device_number = input("Enter the number of the physical drive (e.g., 0 for PhysicalDrive0): ")
    device_path = f"\\\\.\\PhysicalDrive{device_number}"
    output_directory = input("Enter the output directory for recovered files: ")

    # Create a TSK Img_Info object for the storage device
    img_info = pytsk3.Img_Info(device_path)

    # Identify the partition layout using TSK Volume_Info
    try:
        volume_info = pytsk3.Volume_Info(img_info)
    except IOError:
        print("Error: Unable to read partition information. The drive may be encrypted or corrupted.")
        sys.exit(1)

    # List available partitions
    print("Available partitions:")
    for partition in volume_info:
        print(f"Partition {partition.addr}: {partition.desc} (Start: {partition.start}, Length: {partition.len})")

    # User input to select a partition
    partition_number = int(input("Enter the partition number to analyze (e.g., 0 for the first partition): "))

    # Find the selected partition
    selected_partition = None
    for partition in volume_info:
        if partition.addr == partition_number:
            selected_partition = partition
            break

    if not selected_partition:
        print("Error: Partition not found.")
        sys.exit(1)

    # Calculate the offset of the selected partition
    partition_offset = selected_partition.start * volume_info.info.block_size

    # Analyze the file system using the calculated offset
    fs_info = pytsk3.FS_Info(img_info, offset=partition_offset)

    # Find unallocated clusters
    unallocated_clusters = find_unallocated_clusters(img_info, fs_info)

    # Find JPEG images in unallocated clusters
    all_jpegs = []
    cluster_size = fs_info.block_size * fs_info.block_count

    for cluster in unallocated_clusters:
        jpegs = find_jpegs(img_info, fs_info, cluster, cluster_size)
        all_jpegs.extend(jpegs)

    # Recover JPEG images
    recover_jpegs(img_info, all_jpegs, output_directory)

if __name__ == "__main__":
    main()
