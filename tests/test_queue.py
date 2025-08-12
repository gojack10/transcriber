from wrappers.queue_manager import QueueManager, QueueStatus

def test_queue_manager():
    queue_manager = QueueManager()
    item_id = queue_manager.add_item("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    queue_manager.add_item("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    print("Queue counts:", queue_manager.get_queue_counts())
    print("All items:", queue_manager.get_all_items())
    print("All items by status:", queue_manager.get_all_items_by_status(QueueStatus.QUEUED))
    print("Next item:", queue_manager.get_next_item().url if queue_manager.get_next_item() else "None")
    print("Queue counts:", queue_manager.get_queue_counts())
    print("All items:", queue_manager.get_all_items())
    print("All items by status:", queue_manager.get_all_items_by_status(QueueStatus.QUEUED))
    print("Next item:", queue_manager.get_next_item().url if queue_manager.get_next_item() else "None")
    print("Queue counts:", queue_manager.get_queue_counts())

if __name__ == "__main__":
    test_queue_manager()