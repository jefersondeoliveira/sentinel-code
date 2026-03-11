import org.springframework.web.bind.annotation.GetMapping;
import java.util.List;

public class OrderService {

    // PROBLEMA 1: N+1 — busca orders e depois busca items de cada um em loop
    public List<Order> processOrders() {
        List<Order> orders = orderRepository.findAll();
        for (Order order : orders) {
            List<Item> items = itemRepository.findByOrder(order); // N+1 aqui
        }
        return orders;
    }

    // PROBLEMA 2: Cache ausente — getAll sem @Cacheable
    @GetMapping("/products")
    public List<Product> getAllProducts() {
        return productRepository.findAll();
    }
}